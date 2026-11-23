import json
import logging
import os
import re
import sys
import unicodedata
from collections import deque
from difflib import SequenceMatcher

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
if HARNESS not in sys.path:
    sys.path.insert(0, HARNESS)

logging.getLogger("pdfminer").setLevel(logging.ERROR)

PX = 96.0 / 72.0
PAGE_W_PX, PAGE_H_PX, MARGIN_PX = 794, 1123, 57
DEFAULT_PAGE_CSS = "@page{size:A4;margin:15mm}"
INJECT = f'<style id="print-oracle-default">{DEFAULT_PAGE_CSS}</style>'
SMALL_W = 320

_RE_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>|<script\b[^>]*/>", re.I | re.S)
_RE_NOSCRIPT = re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.I | re.S)
_RE_BASE = re.compile(r"<base\b[^>]*>", re.I)
_RE_LINK_REMOTE = re.compile(r"<link\b[^>]*\bhref\s*=\s*[\"']?\s*(?:https?:)?//[^>]*>", re.I)
_RE_IMPORT_REMOTE = re.compile(r"@import\s+(?:url\()?\s*[\"']?\s*(?:https?:)?//[^;]*;", re.I)
_RE_URL_REMOTE = re.compile(r"url\(\s*[\"']?\s*(?:https?:)?//[^)]*\)", re.I)
_RE_SRCSET = re.compile(r"\s(?:srcset|data-src)\s*=\s*(\"[^\"]*\"|'[^']*')", re.I)
_RE_IMG_REMOTE = re.compile(r"(<(?:img|input|source)\b[^>]*?\bsrc\s*=\s*)([\"'])\s*(?:https?:)?//[^\"']*\2", re.I)
_RE_IMG_REMOTE_BARE = re.compile(r"(<(?:img|input|source)\b[^>]*?\bsrc\s*=\s*)(?:https?:)?//[^\s>]+", re.I)
_RE_HEAD = re.compile(r"<head\b[^>]*>", re.I)
_RE_HTML = re.compile(r"<html\b[^>]*>", re.I)
_RE_DOCTYPE = re.compile(r"<!doctype[^>]*>", re.I)
_RE_XMLDECL = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.I)
_VOID = "area|base|br|col|embed|hr|img|input|link|meta|source|track|wbr|param"
_RE_SELFCLOSE = re.compile(r"<((?!(?:" + _VOID + r")\b)[a-zA-Z][\w:-]*)(\s[^<>]*?)?\s*/>")


def xhtml_to_html(s):
    s = _RE_XMLDECL.sub("", s)
    s = _RE_SELFCLOSE.sub(lambda m: f"<{m.group(1)}{m.group(2) or ''}></{m.group(1)}>", s)
    if not _RE_DOCTYPE.search(s[:300]):
        s = "<!DOCTYPE html>\n" + s
    return s


def prepare_html(s, placeholder_rel):
    """Identical static input for Chrome and engines: no JS, no network, default @page first in <head>."""
    s = _RE_SCRIPT.sub("", s)
    s = _RE_NOSCRIPT.sub("", s)
    s = _RE_BASE.sub("", s)
    s = _RE_LINK_REMOTE.sub("", s)
    s = _RE_IMPORT_REMOTE.sub("", s)
    s = _RE_URL_REMOTE.sub("none", s)
    s = _RE_SRCSET.sub("", s)
    s = _RE_IMG_REMOTE.sub(lambda m: f'{m.group(1)}"{placeholder_rel}"', s)
    s = _RE_IMG_REMOTE_BARE.sub(lambda m: f'{m.group(1)}"{placeholder_rel}"', s)
    m = _RE_HEAD.search(s)
    if m:
        return s[:m.end()] + INJECT + s[m.end():]
    m = _RE_HTML.search(s)
    if m:
        return s[:m.end()] + "<head>" + INJECT + "</head>" + s[m.end():]
    m = _RE_DOCTYPE.search(s)
    if m:
        return s[:m.end()] + "<head>" + INJECT + "</head>" + s[m.end():]
    return "<head>" + INJECT + "</head>" + s


def write_placeholder(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (400, 300), (209, 213, 219)).save(path, optimize=False)


# ----------------------------------------------------------------------------- tokens

def _is_cjk(ch):
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF
            or 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0x20000 <= o <= 0x2FA1F
            or 0xFF66 <= o <= 0xFF9F or 0x0E00 <= o <= 0x0E7F)


def _is_complex(ch):
    o = ord(ch)
    return 0x0590 <= o <= 0x08FF or 0x0900 <= o <= 0x0DFF or 0xFB1D <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def _is_word(ch):
    return ch.isalnum() or unicodedata.category(ch) in ("Mn", "Mc")


def norm_token(t):
    t = unicodedata.normalize("NFKC", t).casefold()
    t = "".join(ch for ch in t if _is_word(ch))
    if t and any(_is_complex(ch) for ch in t):
        t = "".join(sorted(t))
    return t


def extract_tokens(pdf_path):
    """Words in pdfminer reading order (text boxes -> lines). Word boundaries come from glyph gaps rather than
    pdfminer's LTAnno spaces: a gap counts as a space when it exceeds min(p25 gap of the line, 0.12em) + 0.15em, so
    letter-spaced text is not split into letters. Returns (pages, tokens); token = [norm, page, x, y] in CSS px, top-left."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTAnno, LTChar, LTContainer, LTTextLine

    lap = LAParams(all_texts=True)
    toks = []
    pages = []
    for pi, pl in enumerate(extract_pages(pdf_path, laparams=lap)):
        X0, Y0, X1, Y1 = pl.bbox
        pages.append([round((X1 - X0) * PX, 2), round((Y1 - Y0) * PX, 2)])
        cur = []

        def flush():
            if cur:
                t = norm_token("".join(c for c, _ in cur))
                if t:
                    x = min(b[0] for _, b in cur)
                    y = min(b[1] for _, b in cur)
                    toks.append([t, pi, round((x - X0) * PX, 2), round((Y1 - y) * PX, 2)])
                cur.clear()

        def feed(item):
            if isinstance(item, LTAnno):
                flush()
                return
            t = item.get_text()
            if not t or not t.strip():
                flush()
                return
            box = (item.x0, item.y1)
            for ch in t:
                if _is_cjk(ch):
                    flush()
                    cur.append((ch, box))
                    flush()
                elif _is_word(ch):
                    cur.append((ch, box))
                else:
                    flush()

        def line(o):
            chars, brk = [], []
            pending = False
            for it in o:
                if isinstance(it, LTChar):
                    t = it.get_text()
                    if not t or not t.strip():
                        pending = True
                        continue
                    chars.append(it)
                    brk.append(pending)
                    pending = False
            gaps = [c.x0 - p.x1 for p, c in zip(chars, chars[1:])]
            srt = sorted(gaps)
            for k, c in enumerate(chars):
                if k:
                    size = max(chars[k - 1].size, c.size, 1.0)
                    base = min(max(srt[len(srt) // 4], 0.0), 0.12 * size)
                    g = gaps[k - 1]
                    if brk[k] or g > base + 0.15 * size or g < -0.5 * size:
                        flush()
                feed(c)
            flush()

        def walk(o):
            if isinstance(o, LTTextLine):
                line(o)
            elif isinstance(o, LTChar):
                feed(o)
            elif isinstance(o, LTContainer):
                for ch in o:
                    walk(ch)
                flush()

        walk(pl)
        flush()
    return pages, toks


# ----------------------------------------------------------------------------- alignment

def align(a_tokens, b_tokens):
    """LCS-style alignment (difflib) on normalized words, then (1) multiset matching inside each 'replace' gap and
    (2) multiset matching of still-unmatched words on the same page index, to recover locally re-ordered words
    (column / text-box order differences). Returns (pairs, n_sequence_matched)."""
    vocab = {}
    a = [vocab.setdefault(t[0], len(vocab)) for t in a_tokens]
    b = [vocab.setdefault(t[0], len(vocab)) for t in b_tokens]
    sm = SequenceMatcher(None, a, b, autojunk=len(a) > 2000 or len(b) > 2000)
    pairs = []
    nseq = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            pairs.extend(zip(range(i1, i2), range(j1, j2)))
            nseq += i2 - i1
        elif tag == "replace":
            pos = {}
            for j in range(j1, j2):
                pos.setdefault(b[j], deque()).append(j)
            for i in range(i1, i2):
                q = pos.get(a[i])
                if q:
                    pairs.append((i, q.popleft()))
    used_a = {i for i, _ in pairs}
    used_b = {j for _, j in pairs}
    pos = {}
    for j in range(len(b)):
        if j not in used_b:
            pos.setdefault((b_tokens[j][1], b[j]), deque()).append(j)
    for i in range(len(a)):
        if i not in used_a:
            q = pos.get((a_tokens[i][1], a[i]))
            if q:
                pairs.append((i, q.popleft()))
    return pairs, nseq


def _pct(v, q):
    return round(float(np.percentile(v, q)), 2) if len(v) else None


def text_metrics(c_tokens, e_tokens):
    pairs, nseq = align(c_tokens, e_tokens)
    nc, ne, nm = len(c_tokens), len(e_tokens), len(pairs)
    same = [(i, j) for i, j in pairs if c_tokens[i][1] == e_tokens[j][1]]
    dx = [abs(e_tokens[j][2] - c_tokens[i][2]) for i, j in same]
    dy = [abs(e_tokens[j][3] - c_tokens[i][3]) for i, j in same]
    return {
        "words_chrome": nc, "words_engine": ne, "words_matched": nm,
        "recall": round(nm / nc, 4) if nc else None,
        "precision": round(nm / ne, 4) if ne else (None if not nc else 0.0),
        "seq_recall": round(nseq / nc, 4) if nc else None,
        "page_agree": round(len(same) / nm, 4) if nm else None,
        "page_agree_strict": round(len(same) / nc, 4) if nc else None,
        "dx_med": _pct(dx, 50), "dx_p90": _pct(dx, 90), "dy_med": _pct(dy, 50), "dy_p90": _pct(dy, 90),
        "pos_within_2px": round(sum(1 for x, y in zip(dx, dy) if x <= 2 and y <= 2) / len(dx), 4) if dx else None,
    }


# ----------------------------------------------------------------------------- raster

def to_gray_small(arr, width=SMALL_W):
    im = Image.fromarray(np.asarray(arr).astype(np.uint8))
    h = max(8, int(im.height * width / im.width))
    return np.asarray(im.convert("L").resize((width, h), Image.BILINEAR), dtype=np.uint8)


def fit(img, h, w):
    if img.shape[:2] == (h, w):
        return img
    canvas = np.full((h, w, 3), 255, dtype=img.dtype)
    hh, ww = min(h, img.shape[0]), min(w, img.shape[1])
    canvas[:hh, :ww] = img[:hh, :ww]
    return canvas


def ssim(a, b):
    from skimage.metrics import structural_similarity
    if a.shape != b.shape:
        h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        a, b = a[:h, :w], b[:h, :w]
    return float(structural_similarity(a.astype(np.float64), b.astype(np.float64), data_range=255))


def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def doc_score(rec):
    if rec.get("status") != "OK":
        return 0.0
    vals = [rec.get(k) for k in ("page_agree_strict", "recall", "precision", "ssim_mean")]
    vals = [v for v in vals if v is not None]
    return round(float(np.mean(vals)), 4) if vals else 0.0

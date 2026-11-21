import os
import re
import unicodedata

import numpy as np
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTContainer
from pypdf import PdfReader
from pypdf.generic import IndirectObject

import common

PX = 96.0 / 72.0


def _walk_chars(obj, out):
    if isinstance(obj, LTChar):
        out.append(obj)
    elif isinstance(obj, LTContainer):
        for o in obj:
            _walk_chars(o, out)


class Char:
    __slots__ = ("t", "x0", "y0", "x1", "y1", "size", "font")

    def __init__(self, t, x0, y0, x1, y1, size, font):
        self.t, self.x0, self.y0, self.x1, self.y1, self.size, self.font = t, x0, y0, x1, y1, size, font

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


class Line:
    def __init__(self, chars):
        self.chars = sorted(chars, key=lambda c: c.x0)
        text, boxes = [], []
        prev = None
        for c in self.chars:
            if prev is not None:
                gap = c.x0 - prev.x1
                if gap > max(1.5, 0.22 * max(prev.size, 1)):
                    text.append(" ")
                    boxes.append(None)
            text.append(c.t)
            boxes.extend([c] * len(c.t))
            prev = c
        self.text = "".join(text)
        self.boxes = boxes
        self.x0 = min(c.x0 for c in self.chars)
        self.x1 = max(c.x1 for c in self.chars)
        self.y0 = min(c.y0 for c in self.chars)
        self.y1 = max(c.y1 for c in self.chars)


class PdfDoc:
    def __init__(self, path, raster_dir=None):
        self.path = path
        self.reader = PdfReader(path)
        self.pages = []
        lap = LAParams(line_margin=0.3, char_margin=2.0, word_margin=0.1, all_texts=True)
        for pl in extract_pages(path, laparams=lap):
            X0, Y0, X1, Y1 = pl.bbox
            raw = []
            _walk_chars(pl, raw)
            chars = []
            for c in raw:
                t = c.get_text()
                if not t or t.isspace():
                    continue
                chars.append(Char(t, (c.x0 - X0) * PX, (Y1 - c.y1) * PX, (c.x1 - X0) * PX, (Y1 - c.y0) * PX,
                                  c.size * PX, c.fontname))
            self.pages.append({"w": (X1 - X0) * PX, "h": (Y1 - Y0) * PX, "chars": chars, "lines": self._lines(chars)})
        self._raster = None
        self._raster_dir = raster_dir

    @staticmethod
    def _lines(chars):
        rows = []
        for c in sorted(chars, key=lambda c: (c.cy, c.x0)):
            h = max(c.y1 - c.y0, 1)
            placed = False
            for r in rows:
                if abs(r["cy"] - c.cy) < 0.45 * max(h, r["h"]):
                    r["chars"].append(c)
                    placed = True
                    break
            if not placed:
                rows.append({"cy": c.cy, "h": h, "chars": [c]})
        lines = []
        for r in rows:
            cs = sorted(r["chars"], key=lambda c: c.x0)
            seg = [cs[0]]
            for c in cs[1:]:
                if c.x0 - seg[-1].x1 > 3.0 * max(seg[-1].size, 1):
                    lines.append(Line(seg))
                    seg = [c]
                else:
                    seg.append(c)
            lines.append(Line(seg))
        lines.sort(key=lambda l: (round(l.y0, 0), l.x0))
        return lines

    @property
    def n(self):
        return len(self.pages)

    def find(self, token):
        hits = []
        for pi, p in enumerate(self.pages):
            for ln in p["lines"]:
                start = 0
                while True:
                    k = ln.text.find(token, start)
                    if k < 0:
                        break
                    bx = [b for b in ln.boxes[k:k + len(token)] if b is not None]
                    if bx:
                        hits.append({"page": pi, "x0": min(b.x0 for b in bx), "x1": max(b.x1 for b in bx),
                                     "y0": min(b.y0 for b in bx), "y1": max(b.y1 for b in bx)})
                    start = k + 1
        return hits

    def page_text(self, pi):
        return "\n".join(l.text for l in self.pages[pi]["lines"])

    def all_text(self):
        return "\n".join(self.page_text(i) for i in range(self.n))

    def raster(self):
        if self._raster is None:
            d = self._raster_dir or (self.path + "_px")
            files = common.rasterize(self.path, d)
            self._raster = [common.load_rgb(f) for f in files]
        return self._raster

    def pixel(self, pi, x, y, r=2):
        img = self.raster()[pi]
        h, w = img.shape[:2]
        xi, yi = int(round(x)), int(round(y))
        x0, x1 = max(0, xi - r), min(w, xi + r + 1)
        y0, y1 = max(0, yi - r), min(h, yi + r + 1)
        if x0 >= x1 or y0 >= y1:
            return None
        reg = img[y0:y1, x0:x1].reshape(-1, 3)
        return tuple(int(v) for v in np.median(reg, axis=0))

    def page_size_pt(self, pi):
        mb = self.reader.pages[pi].mediabox
        return float(mb.width), float(mb.height)

    def links(self):
        out = []
        for pi, page in enumerate(self.reader.pages):
            annots = page.get("/Annots")
            if annots is None:
                continue
            if isinstance(annots, IndirectObject):
                annots = annots.get_object()
            mb = page.mediabox
            for a in annots:
                a = a.get_object()
                if a.get("/Subtype") != "/Link":
                    continue
                rect = [float(v) for v in a.get("/Rect", [0, 0, 0, 0])]
                x0, y0, x1, y1 = min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3])
                H = float(mb.top)
                L = float(mb.left)
                entry = {"page": pi, "x0": (x0 - L) * PX, "x1": (x1 - L) * PX, "y0": (H - y1) * PX, "y1": (H - y0) * PX}
                act = a.get("/A")
                act = act.get_object() if act is not None else None
                if act is not None and act.get("/S") == "/URI":
                    entry["uri"] = str(act.get("/URI"))
                else:
                    dest = a.get("/Dest")
                    if dest is None and act is not None and act.get("/S") == "/GoTo":
                        dest = act.get("/D")
                    entry["dest_page"] = self._dest_page(dest)
                out.append(entry)
        return out

    def _dest_page(self, dest):
        try:
            if dest is None:
                return None
            dest = dest.get_object() if hasattr(dest, "get_object") else dest
            if isinstance(dest, (str, bytes)) or type(dest).__name__ in ("TextStringObject", "ByteStringObject", "NameObject"):
                named = self.reader.named_destinations
                key = str(dest)
                if key in named:
                    return self.reader.get_destination_page_number(named[key])
                return None
            arr = dest
            if hasattr(arr, "get") and "/D" in arr:
                arr = arr["/D"]
            pref = arr[0]
            for i, p in enumerate(self.reader.pages):
                if p.indirect_reference is not None and pref.idnum == p.indirect_reference.idnum:
                    return i
        except Exception:
            return None
        return None

    def outline(self):
        res = []

        def walk(items, depth):
            for it in items:
                if isinstance(it, list):
                    walk(it, depth + 1)
                else:
                    try:
                        pg = self.reader.get_destination_page_number(it)
                    except Exception:
                        pg = None
                    res.append({"title": str(it.title).strip(), "depth": depth, "page": pg})
        try:
            walk(self.reader.outline, 0)
        except Exception:
            pass
        return res

    def metadata(self):
        m = self.reader.metadata or {}
        return {"title": str(m.get("/Title", "") or ""), "author": str(m.get("/Author", "") or "")}

    def fonts(self):
        seen = {}

        def scan_res(res):
            if res is None:
                return
            res = res.get_object()
            fonts = res.get("/Font")
            if fonts is not None:
                fonts = fonts.get_object()
                for _, f in fonts.items():
                    f = f.get_object()
                    name = str(f.get("/BaseFont", f.get("/Name", "?")))
                    sub = str(f.get("/Subtype"))
                    emb = sub == "/Type3"
                    desc = None
                    if sub == "/Type0":
                        df = f["/DescendantFonts"][0].get_object()
                        desc = df.get("/FontDescriptor")
                    else:
                        desc = f.get("/FontDescriptor")
                    if desc is not None:
                        desc = desc.get_object()
                        emb = emb or any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))
                    seen[name] = {"subtype": sub, "embedded": bool(emb)}
            xo = res.get("/XObject")
            if xo is not None:
                for _, x in xo.get_object().items():
                    x = x.get_object()
                    if x.get("/Subtype") == "/Form":
                        scan_res(x.get("/Resources"))
        for p in self.reader.pages:
            scan_res(p.get("/Resources"))
        return seen

    def has_struct_tree(self):
        root = self.reader.trailer["/Root"].get_object()
        return "/StructTreeRoot" in root

    def out_of_bounds_chars(self, tol=1.0):
        bad = []
        for pi, p in enumerate(self.pages):
            for c in p["chars"]:
                if c.x0 < -tol or c.y0 < -tol or c.x1 > p["w"] + tol or c.y1 > p["h"] + tol:
                    bad.append((pi, c.t, round(c.x0, 1), round(c.y0, 1)))
        return bad

    def overlapping_lines(self, min_frac=0.35):
        count = 0
        examples = []
        for pi, p in enumerate(self.pages):
            ls = p["lines"]
            for i in range(len(ls)):
                a = ls[i]
                for j in range(i + 1, len(ls)):
                    b = ls[j]
                    if b.y0 > a.y1:
                        break
                    ix = min(a.x1, b.x1) - max(a.x0, b.x0)
                    iy = min(a.y1, b.y1) - max(a.y0, b.y0)
                    if ix <= 0 or iy <= 0:
                        continue
                    area = ix * iy
                    small = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
                    if small > 0 and area / small > min_frac:
                        count += 1
                        if len(examples) < 5:
                            examples.append((pi, a.text[:30], b.text[:30]))
        return count, examples


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s)


def close(rgb, target, tol):
    return rgb is not None and all(abs(a - b) <= tol for a, b in zip(rgb, target))

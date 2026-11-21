#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import tempfile

import pyphen

LANGS = [
    ("en", "en_US", "en_US"),
    ("de", "de_DE", "de_DE"),
    ("fr", "fr_FR", "fr"),
    ("es", "es_ES", "es"),
    ("it", "it_IT", "it_IT"),
    ("pt", "pt_PT", "pt_PT"),
    ("nl", "nl_NL", "nl_NL"),
    ("ru", "ru_RU", "ru_RU"),
]
HUNSPELL_DIR = "/usr/share/hunspell"
WORDS_PER_LANG = 10000
MIN_LEN = 5
PERMISSIVE = {"MIT", "APACHE", "BSD", "PUBLIC DOMAIN", "CC0", "UNLICENSE"}
MIT_APACHE = {"MIT", "APACHE"}
COPYLEFT_OR_OTHER = ("LPPL", "MPL", "GPL", "LGPL")

GEN_RE = re.compile(r'\("([^"]+)",\s*"([a-z]{2})",\s*&\[[^\]]*\],\s*"(\w{4})",\s*"([^"]+)",\s*(\d+),\s*(\d+)\)')


def parse_generate(repo):
    src = open(os.path.join(repo, "tests", "generate.rs"), encoding="utf-8").read()
    out = {}
    for name, iso, script, fname, left, right in GEN_RE.findall(src):
        out[iso] = {"language": name, "iso": iso, "script": script, "pattern_file": fname,
                    "bounds": [int(left), int(right)]}
    return out


def licence_block(text):
    lines = text.splitlines()
    block = []
    inside = False
    for line in lines[:400]:
        if re.match(r"^%\s*licen[cs]e\s*:", line, re.I):
            inside = True
            continue
        if inside:
            if re.match(r"^%\s?\S[^:]*:\s*", line) and not re.match(r"^%\s{2,}", line):
                break
            if not line.startswith("%"):
                break
            block.append(line[1:])
    return "\n".join(block)


def classify(block, whole):
    names = []
    for m in re.finditer(r"name\s*:\s*(.+)", block):
        names.append(m.group(1).strip().strip("'\""))
    versions = re.findall(r"version\s*:\s*([\w.]+)", block)
    choice = bool(re.search(r"at your option|any of these", block, re.I))
    norm = []
    for n in names:
        u = n.upper()
        if "LPPL" in u or "LATEX PROJECT" in u:
            norm.append("LPPL")
        elif "LGPL" in u:
            norm.append("LGPL")
        elif "GPL" in u:
            norm.append("GPL")
        elif "MPL" in u or "MOZILLA" in u:
            norm.append("MPL")
        elif "MIT" in u:
            norm.append("MIT")
        elif "BSD" in u:
            norm.append("BSD")
        elif "APACHE" in u:
            norm.append("APACHE")
        elif "UNLICEN" in u:
            norm.append("UNLICENSE")
        elif "PUBLIC" in u:
            norm.append("PUBLIC DOMAIN")
        else:
            norm.append(n)
    header = whole.split("\\patterns{", 1)[0]
    if not norm:
        if re.search(r"Copying and distribution of this file, with or without modification", block):
            norm.append("ALL-PERMISSIVE (FSF all-permissive notice)")
        elif re.search(r"LaTeX Project Public License|LPPL", block or header):
            norm.append("LPPL")
        elif not block.strip() and re.search(r"MIT License|Permission is hereby granted, free of charge", header):
            norm.append("MIT")
        elif block.strip():
            norm.append("CUSTOM TEXT (manual review)")
        else:
            norm.append("NO LICENCE STATEMENT FOUND")
    has_mit_apache = any(n in MIT_APACHE for n in norm)
    permissive_option = any(n in PERMISSIVE or n.startswith("ALL-PERMISSIVE") for n in norm)
    non_mit_apache = [n for n in norm if n not in MIT_APACHE]
    return {
        "licences": norm,
        "versions": versions,
        "alternatives_at_users_option": choice or len(norm) > 1,
        "mit_or_apache_available": has_mit_apache,
        "permissive_option_available": permissive_option,
        "non_mit_apache_licences": non_mit_apache,
        "flag": bool(non_mit_apache) and not has_mit_apache,
        "contains_copyleft_or_lppl": any(n in COPYLEFT_OR_OTHER for n in norm),
        "licence_text_excerpt": re.sub(r"\s+", " ", block)[:400],
    }


def tex_patterns(text):
    out = []
    i = 0
    while True:
        j = text.find("\\patterns{", i)
        if j < 0:
            break
        k = text.find("}", j)
        body = text[j + len("\\patterns{"):k]
        for line in body.splitlines():
            line = line.split("%", 1)[0]
            out.extend(t for t in line.split() if t)
        i = k + 1
    return out


def tex_exceptions(text):
    out = {}
    j = text.find("\\hyphenation{")
    if j < 0:
        return out
    k = text.find("}", j)
    body = text[j + len("\\hyphenation{"):k]
    for line in body.splitlines():
        line = line.split("%", 1)[0]
        for t in line.split():
            word = t.replace("-", "")
            pos, n = [], 0
            for ch in t:
                if ch == "-":
                    pos.append(n)
                else:
                    n += 1
            out[word] = pos
    return out


def aff_encoding(aff):
    try:
        with open(aff, "rb") as fh:
            for raw in fh:
                m = re.match(rb"^\s*SET\s+(\S+)", raw)
                if m:
                    enc = m.group(1).decode("ascii").lower()
                    return {"microsoft-cp1251": "cp1251"}.get(enc, enc)
    except OSError:
        pass
    return "utf-8"


def wordlist(base):
    dic = os.path.join(HUNSPELL_DIR, base + ".dic")
    aff = os.path.join(HUNSPELL_DIR, base + ".aff")
    enc = aff_encoding(aff)
    words = set()
    with open(dic, encoding=enc, errors="replace") as fh:
        next(fh, None)
        for line in fh:
            w = line.split("/", 1)[0].split("\t", 1)[0].strip()
            if len(w) >= MIN_LEN and w.isalpha() and w == w.lower():
                words.add(w)
    words = sorted(words)
    if len(words) > WORDS_PER_LANG:
        step = len(words) / WORDS_PER_LANG
        words = [words[int(i * step)] for i in range(WORDS_PER_LANG)]
    return dic, enc, words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hypher-repo", required=True)
    ap.add_argument("--hypher-sha", required=True)
    ap.add_argument("--out-ref", required=True)
    ap.add_argument("--out-licences", required=True)
    args = ap.parse_args()
    gen = parse_generate(args.hypher_repo)
    pat_dir = os.path.join(args.hypher_repo, "patterns")

    inventory = []
    for iso, info in sorted(gen.items()):
        text = open(os.path.join(pat_dir, info["pattern_file"]), encoding="utf-8").read()
        rec = dict(info)
        rec.update(classify(licence_block(text), text))
        inventory.append(rec)
    flagged = [r for r in inventory if r["flag"]]
    copyleft = [r for r in inventory if r["contains_copyleft_or_lppl"]]
    lic_result = {
        "test": "hyphenation_licences",
        "hypher_version": "0.1.8",
        "hypher_repo_sha": args.hypher_sha,
        "source": "patterns/*.tex in https://github.com/typst/hypher at the commit recorded in the crates.io package (.cargo_vcs_info.json); the .crate excludes patterns/ but embeds tries built from them",
        "pass": len(inventory) - len(flagged),
        "fail": len(flagged),
        "total": len(inventory),
        "pass_rate": (len(inventory) - len(flagged)) / len(inventory) if inventory else 0.0,
        "pass_criterion": "a language passes if MIT or Apache-2.0 is among the licences the pattern file may be used under",
        "languages_with_copyleft_or_lppl_terms": [r["iso"] for r in copyleft],
        "inventory": inventory,
        "first_failures": [{"iso": r["iso"], "file": r["pattern_file"], "licences": r["licences"]} for r in flagged[:20]],
    }
    with open(args.out_licences, "w", encoding="utf-8") as fh:
        json.dump(lic_result, fh, ensure_ascii=False, indent=1)

    langs = []
    tmpdir = tempfile.mkdtemp()
    for iso, hunspell_base, pyphen_lang in LANGS:
        info = gen[iso]
        left, right = info["bounds"]
        text = open(os.path.join(pat_dir, info["pattern_file"]), encoding="utf-8").read()
        pats = tex_patterns(text)
        dic_path = os.path.join(tmpdir, f"hyph_{iso}_tex.dic")
        with open(dic_path, "w", encoding="utf-8") as fh:
            fh.write("UTF-8\n")
            fh.write("\n".join(pats))
            fh.write("\n")
        same = pyphen.Pyphen(filename=dic_path, left=left, right=right)
        pyphen_resolved = pyphen.language_fallback(pyphen_lang)
        dict_ref = pyphen.Pyphen(lang=pyphen_resolved, left=left, right=right)
        exceptions = tex_exceptions(text)
        src, enc, words = wordlist(hunspell_base)
        ref_same = [[int(p) for p in same.positions(w)] for w in words]
        ref_dict = [[int(p) for p in dict_ref.positions(w)] for w in words]
        exc_hits = {w: [p for p in exceptions[w] if left <= p <= len(w) - right] for w in words if w in exceptions}
        langs.append({
            "iso": iso,
            "pattern_file": info["pattern_file"],
            "pattern_count": len(pats),
            "bounds": [left, right],
            "wordlist_source": src,
            "wordlist_encoding": enc,
            "pyphen_dictionary": str(pyphen.LANGUAGES[pyphen_resolved].name),
            "tex_exception_count": len(exceptions),
            "tex_exceptions_in_wordlist": exc_hits,
            "words": words,
            "ref_same_patterns": ref_same,
            "ref_pyphen_dictionary": ref_dict,
        })
        print(f"{iso}: {len(words)} words, {len(pats)} patterns, {len(exc_hits)} exception words in list")
    with open(args.out_ref, "w", encoding="utf-8") as fh:
        json.dump({"pyphen_version": pyphen.__version__, "hypher_sha": args.hypher_sha, "languages": langs}, fh, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

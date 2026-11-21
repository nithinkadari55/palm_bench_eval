#!/usr/bin/env python3
"""Navigation checks: link targets and rects, outline hierarchy and destinations, named destinations, labels, metadata."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pikepdf  # noqa: E402
import pypdf  # noqa: E402
from pypdf.generic import ArrayObject, ByteStringObject, IndirectObject, TextStringObject  # noqa: E402

TOL = 1.0


def close(a, b, tol=TOL):
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def norm_rect(r):
    x0, y0, x1, y1 = [float(v) for v in r]
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def page_index_map(reader):
    return {p.indirect_reference.idnum: i for i, p in enumerate(reader.pages)}


def resolve(o):
    return o.get_object() if isinstance(o, IndirectObject) else o


def explicit_dest(arr, pmap):
    arr = resolve(arr)
    if isinstance(arr, dict) and "/D" in arr:
        arr = resolve(arr["/D"])
    if not isinstance(arr, ArrayObject) or not arr:
        return None
    pref = arr[0]
    page = pmap.get(pref.idnum) if isinstance(pref, IndirectObject) else (int(pref) if isinstance(pref, int) else None)
    kind = str(arr[1]) if len(arr) > 1 else None
    top = float(arr[3]) if kind == "/XYZ" and len(arr) > 3 and arr[3] is not None else None
    return {"page": page, "kind": kind, "top": top}


def outline_tree(reader, items, pmap):
    out = []
    for it in items:
        if isinstance(it, list):
            if out:
                out[-1]["children"] = outline_tree(reader, it, pmap)
            continue
        page = reader.get_destination_page_number(it)
        top = float(it.top) if getattr(it, "top", None) is not None else None
        out.append({"title": it.title, "page": page, "top": top, "children": []})
    return out


def cmp_outline(got, want, path=""):
    if len(got) != len(want):
        return f"{path}: {len(got)} items, want {len(want)}"
    for i, (g, w) in enumerate(zip(got, want)):
        p = f"{path}/{w['title']}"
        if g["title"] != w["title"] or g["page"] != w["page"]:
            return f"{p}: got title={g['title']!r} page={g['page']}, want page={w['page']}"
        if g["top"] is None or abs(g["top"] - w["top_pdf"]) > TOL:
            return f"{p}: top {g['top']} want {w['top_pdf']}"
        r = cmp_outline(g["children"], w["children"], p)
        if r:
            return r
    return None


def check_navigation(path, profile, exp):
    rows = []

    def add(name, ok, detail=None):
        rows.append({"fixture": "navigation", "profile": profile, "check": name, "pass": bool(ok), "detail": detail})

    r = pypdf.PdfReader(path)
    pmap = page_index_map(r)
    add("page_count", len(r.pages) == exp["page_count"], len(r.pages))
    labels = list(r.page_labels)
    add("page_labels", labels == exp["page_labels"], labels)
    sizes = [[round(float(p.mediabox.width), 2), round(float(p.mediabox.height), 2)] for p in r.pages]
    add("page_size", all(close(s, exp["page_size"], 0.05) for s in sizes), sizes[:2])
    named = {}
    try:
        named = r.named_destinations
    except Exception as e:
        add("named_destinations_readable", False, repr(e))
    for lk in exp["links"]:
        page = r.pages[lk["page"]]
        annots = [resolve(a) for a in (page.get("/Annots") or [])]
        cand = [a for a in annots if str(a.get("/Subtype")) == "/Link" and close(norm_rect(a["/Rect"]), norm_rect(lk["rect_pdf"]))]
        name = f"link_{lk['kind']}"
        if not cand:
            add(name + "_rect", False, {"want": lk["rect_pdf"], "have": [[round(float(v), 2) for v in a.get("/Rect", [])] for a in annots]})
            continue
        add(name + "_rect", True)
        a = cand[0]
        add(name + "_alt_contents", str(a.get("/Contents", "")) == lk["text"], str(a.get("/Contents", "")))
        if lk["kind"] == "uri":
            act = resolve(a.get("/A"))
            ok = act is not None and str(act.get("/S")) == "/URI" and str(act.get("/URI")) == lk["uri"]
            add(name + "_target", ok, {k: str(v) for k, v in (act or {}).items()})
            continue
        dest = a.get("/Dest")
        if dest is None and a.get("/A") is not None:
            act = resolve(a["/A"])
            dest = act.get("/D") if str(act.get("/S")) == "/GoTo" else None
        dest = resolve(dest)
        if lk["kind"] == "named":
            is_name = isinstance(dest, (TextStringObject, ByteStringObject, str))
            add(name + "_is_named", is_name, type(dest).__name__)
            nm = str(dest) if is_name else None
            d = named.get(nm) if nm else None
            got_page = r.get_destination_page_number(d) if d is not None else None
            top = float(d.top) if d is not None and getattr(d, "top", None) is not None else None
            add(name + "_target", got_page == lk["target_page"] and top is not None and abs(top - lk["target_top_pdf"]) <= TOL,
                {"name": nm, "page": got_page, "top": top})
        else:
            ed = explicit_dest(dest, pmap)
            ok = ed is not None and ed["page"] == lk["target_page"] and ed["kind"] == "/XYZ" and ed["top"] is not None and abs(ed["top"] - lk["target_top_pdf"]) <= TOL
            add(name + "_target", ok, ed)
    try:
        got = outline_tree(r, r.outline, pmap)
        diff = cmp_outline(got, exp["outline"])
        add("outline_hierarchy_and_destinations", diff is None, diff)
    except Exception as e:
        add("outline_hierarchy_and_destinations", False, repr(e))
    bad = {}
    for nm, pg in exp["named_destinations"].items():
        d = named.get(nm)
        gp = r.get_destination_page_number(d) if d is not None else None
        if gp != pg:
            bad[nm] = gp
    add("named_destinations", not bad, {"bad": bad, "names": sorted(named)[:10]})
    md = r.metadata or {}
    add("metadata_title", md.get("/Title") == exp["title"] or _xmp_title(path) == exp["title"], {"info": md.get("/Title"), "xmp": _xmp_title(path)})
    add("metadata_author", md.get("/Author") == exp["author"] or exp["author"] in (_xmp(path, "dc:creator") or ""), {"info": md.get("/Author"), "xmp": _xmp(path, "dc:creator")})
    root = r.trailer["/Root"]
    add("metadata_lang", str(root.get("/Lang", "")) == exp["lang"], str(root.get("/Lang", "")))
    return rows


def _xmp(path, key):
    try:
        with pikepdf.open(path) as pdf:
            m = pdf.open_metadata()
            v = m.get(key)
            return str(v) if v is not None else None
    except Exception:
        return None


def _xmp_title(path):
    return _xmp(path, "dc:title")


def check_structure_link(path, profile, exp):
    rows = []
    r = pypdf.PdfReader(path)
    for lk in exp.get("links", []):
        page = r.pages[lk["page"]]
        annots = [resolve(a) for a in (page.get("/Annots") or [])]
        cand = [a for a in annots if close(norm_rect(a["/Rect"]), norm_rect(lk["rect_pdf"]))]
        ok = bool(cand) and str(resolve(cand[0].get("/A", {})).get("/URI", "")) == lk["uri"]
        rows.append({"fixture": "structure", "profile": profile, "check": "link_uri_rect_and_target", "pass": ok, "detail": None if ok else lk})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    nav_exp = json.load(open(os.path.join(args.corpus, "navigation", "expected.json"), encoding="utf-8"))
    st_path = os.path.join(args.corpus, "structure", "expected.json")
    st_exp = json.load(open(st_path, encoding="utf-8")) if os.path.exists(st_path) else {}
    rows = []
    for e in gen["entries"]:
        if e["status"] != "ok":
            continue
        path = os.path.join(args.corpus, e["file"])
        try:
            if e["fixture"] == "navigation":
                rows += check_navigation(path, e["profile"], nav_exp)
            elif e["fixture"] == "structure":
                rows += check_structure_link(path, e["profile"], st_exp)
        except Exception as ex:
            rows.append({"fixture": e["fixture"], "profile": e["profile"], "check": "inspection", "pass": False, "detail": repr(ex)[:500]})
    per_check, per_profile, matrix = {}, {}, {}
    for r_ in rows:
        for d, k in ((per_check, r_["check"]), (per_profile, r_["profile"])):
            a = d.setdefault(k, {"pass": 0, "total": 0})
            a["total"] += 1
            a["pass"] += r_["pass"]
        if r_["fixture"] == "navigation":
            matrix.setdefault(r_["check"], {})[r_["profile"]] = r_["pass"]
    passed = sum(r_["pass"] for r_ in rows)
    result = {
        "test": f"navigation_{args.label}",
        "tools": {"pypdf": pypdf.__version__, "pikepdf": pikepdf.__version__},
        "pass": passed, "fail": len(rows) - passed, "total": len(rows),
        "pass_rate": passed / len(rows) if rows else None,
        "pass_criterion": f"link annotation /Rect within {TOL} pt of the intended rect, URI / explicit XYZ / named destination resolve to the intended page and top (within {TOL} pt), link /Contents alt text, outline titles+hierarchy+pages+tops, registered named destinations, page labels i, ii, 1..4, Info/XMP title and author, catalog /Lang",
        "per_check": per_check, "per_profile": per_profile, "navigation_matrix": matrix,
        "first_failures": [r_ for r_ in rows if not r_["pass"]][:40],
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, default=str)
    print(f"navigation: {passed}/{len(rows)} checks pass")


if __name__ == "__main__":
    main()

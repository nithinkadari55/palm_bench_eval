#!/usr/bin/env python3
"""Structure and accessibility checks: tags, alt text, table header scope, reading order, Lang, artifacts, page labels."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pikepdf  # noqa: E402

from pdfinspect import marked_content, norm, page_labels, struct_roles_pypdf, struct_tree_pikepdf  # noqa: E402

UA = ("ua1",)


def check_file(path, fixture, profile, exp, pdf_version):
    res = []

    def add(name, ok, detail=None):
        res.append({"fixture": fixture, "profile": profile, "check": name, "pass": bool(ok), "detail": detail})

    pdf = pikepdf.open(path)
    root = pdf.Root
    mark = root.get("/MarkInfo")
    st = struct_tree_pikepdf(pdf)
    add("tagged", st is not None and mark is not None and bool(mark.get("/Marked", False)),
        {"struct_tree": st is not None, "marked": bool(mark.get("/Marked", False)) if mark is not None else None})
    add("document_lang", str(root.get("/Lang", "")) == exp.get("lang", "en"), str(root.get("/Lang", "")))
    if any(u in profile.split("+") for u in UA):
        vp = root.get("/ViewerPreferences")
        add("display_doc_title", vp is not None and bool(vp.get("/DisplayDocTitle", False)), None)
    if st is None:
        pdf.close()
        return res
    elems, leaves, parent_tree, info = st
    mc = marked_content(path)

    untagged = [norm(p["untagged"]) for p in mc if norm(p["untagged"])]
    add("no_untagged_text", not untagged, untagged[:3])

    roles_pk = [(e["role"], e["depth"], e["alt"]) for e in elems]
    roles_py = struct_roles_pypdf(path)
    add("pypdf_pikepdf_agree", roles_py == roles_pk,
        None if roles_py == roles_pk else {"pikepdf": roles_pk[:15], "pypdf": (roles_py or [])[:15]})

    std_roles = {e["std"] for e in elems}
    if exp.get("figure_alts"):
        alts = [norm(e["alt"]) for e in elems if e["std"] == "Figure"]
        missing = [a for a in exp["figure_alts"] if norm(a) not in alts]
        add("figure_alt_text", not missing, {"missing": missing[:5], "figures": len(alts)})

    if exp.get("page_labels"):
        got = page_labels(path)
        add("page_labels", got == exp["page_labels"], None if got == exp["page_labels"] else {"got": got[:12], "want": exp["page_labels"][:12]})

    def mcid_text(page, mcid):
        if page is None or page >= len(mc):
            return ""
        return mc[page]["mcid"].get(mcid, "")

    # artifacts (running headers / footers)
    header_texts = exp.get("headers") or ([exp["header"]] * exp.get("page_count", 0) if exp.get("header") else None)
    if header_texts:
        bad = []
        sub_ok = True
        for i, h in enumerate(header_texts):
            if i >= len(mc):
                bad.append(f"page {i} missing")
                continue
            arts = mc[i]["artifacts"]
            hit = [a for a in arts if norm(h) in norm(a["text"])]
            in_mcid = any(norm(h) in norm(t) for t in mc[i]["mcid"].values())
            if not hit or in_mcid:
                bad.append({"page": i, "artifact_hit": bool(hit), "inside_structure": in_mcid})
            elif pdf_version >= "PDF 1.7" and not any(a["props"].get("Subtype") in ("Header", "/Header") for a in hit):
                sub_ok = False
        add("header_artifacts", not bad, bad[:5])
        if pdf_version >= "PDF 1.7":
            add("header_artifact_subtype", sub_ok, "artifact property list carries /Subtype /Header (PDF >= 1.7)")
    if exp.get("footers"):
        bad = [i for i, ftxt in enumerate(exp["footers"]) if i >= len(mc) or not any(norm(ftxt) in norm(a["text"]) for a in mc[i]["artifacts"])]
        add("footer_artifacts", not bad, bad[:5])

    if fixture in ("text", "text_emoji"):
        bad = []
        for pg in exp["pages"]:
            if pg["script"] == "variable":
                continue
            owners = [elems[l["elem"]] for l in leaves if l["kind"] == "mcid" and l["page"] == pg["page"]]
            langs = set()
            for o in owners:
                cur = o
                while cur is not None and cur["lang"] is None and cur["parent"] is not None:
                    cur = elems[cur["parent"]]
                langs.add(cur["lang"] if cur else None)
            if langs != {pg["lang"]}:
                bad.append({"script": pg["script"], "want": pg["lang"], "got": sorted(map(str, langs))})
        add("element_lang_per_script", not bad, bad)

    if fixture == "structure":
        req = set(exp["required_roles"])
        add("required_roles_present", req <= std_roles, {"missing": sorted(req - std_roles), "optional_present": sorted(set(exp["optional_roles"]) & std_roles)})
        add("table_sections_THead_TBody", set(exp["optional_roles"]) <= std_roles, sorted(std_roles))
        # reading order: text of the structure leaves in DFS order vs the order the generator tagged
        got = []
        for l in leaves:
            if l["kind"] != "mcid":
                continue
            t = norm(mcid_text(l["page"], l["mcid"]))
            if t:
                got.append(t)
        want = [norm(o["text"]) for o in exp["reading_order"] if o.get("text")]
        add("reading_order", got == want, None if got == want else {"first_mismatch": next(({"i": i, "got": g, "want": w} for i, (g, w) in enumerate(zip(got, want)) if g != w), {"len_got": len(got), "len_want": len(want)})})
        ths = [e for e in elems if e["std"] == "TH"]
        scopes = []
        for e in ths:
            sc = None
            for a in e["attrs"]:
                if a.get("/O") == "/Table" and "/Scope" in a:
                    sc = a["/Scope"].lstrip("/")
            scopes.append(sc)
        want_sc = [t["scope"] for t in exp["th_scopes"]]
        add("table_header_scope", scopes == want_sc, None if scopes == want_sc else {"got": scopes, "want": want_sc})
        heads = [e for e in elems if e["std"] in ("H1", "H2", "H3")]
        add("heading_titles", heads and all(e["title"] for e in heads), [e["std"] for e in heads if not e["title"]])
        fr = [e for e in elems if e["lang"] == "fr"]
        fr_text = [norm("".join(mcid_text(p, m) for p, m in e["mcids"])) for e in fr]
        want_fr = [norm(s["text"]) for s in exp["span_langs"]]
        add("span_lang", any(w in fr_text for w in want_fr), {"fr_elements": fr_text})
        # Link elements must reference their annotation (OBJR) and the annotation must point back via the ParentTree
        links = [e for e in elems if e["std"] == "Link"]
        bad = []
        annots = {}
        for page in pdf.pages:
            for a in page.obj.get("/Annots", []):
                annots[a.objgen] = a
        for e in links:
            if not e["objr"]:
                bad.append({"link": e["objgen"], "error": "no OBJR"})
                continue
            for og in e["objr"]:
                a = annots.get(og)
                if a is None or "/StructParent" not in a:
                    bad.append({"link": e["objgen"], "error": "annotation missing or without /StructParent"})
                    continue
                target = parent_tree.get(int(a["/StructParent"]))
                if target is None or getattr(target, "objgen", None) != e["objgen"]:
                    bad.append({"link": e["objgen"], "error": "ParentTree entry does not point to the Link element"})
        add("link_objr_parent_tree", links and not bad, {"links": len(links), "problems": bad[:5]})
        pages_with_sp = all("/StructParents" in p.obj for p in pdf.pages)
        add("page_struct_parents", pages_with_sp and info["parent_tree_keys"] > 0, info)
    pdf.close()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    exps = {}
    rows = []
    for e in gen["entries"]:
        if e["status"] != "ok":
            continue
        fx = e["fixture"]
        if fx not in exps:
            p = os.path.join(args.corpus, fx, "expected.json")
            exps[fx] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        path = os.path.join(args.corpus, e["file"])
        try:
            rows += check_file(path, fx, e["profile"], exps[fx], e.get("pdf_version", ""))
        except Exception as ex:
            rows.append({"fixture": fx, "profile": e["profile"], "check": "inspection", "pass": False, "detail": repr(ex)[:500]})

    def agg(key):
        d = {}
        for r in rows:
            a = d.setdefault(r[key], {"pass": 0, "total": 0})
            a["total"] += 1
            a["pass"] += r["pass"]
        return d

    matrix = {}
    for r in rows:
        if r["fixture"] in ("structure",):
            matrix.setdefault(r["check"], {})[r["profile"]] = r["pass"]
    passed = sum(r["pass"] for r in rows)
    result = {
        "test": f"structure_{args.label}",
        "tools": {"pikepdf": pikepdf.__version__},
        "pass": passed, "fail": len(rows) - passed, "total": len(rows),
        "pass_rate": passed / len(rows) if rows else None,
        "pass_criterion": "each structural check holds for the generated PDF: StructTreeRoot + /MarkInfo /Marked, catalog /Lang, no untagged text, pypdf and pikepdf see the same tree, every Figure alt text, page labels, header/footer text only inside /Artifact, per-script /Lang, required roles, reading order equal to the generator's tagging order, TH /Scope, heading titles, /Lang fr span, Link OBJR <-> ParentTree, /StructParents on pages, /DisplayDocTitle for PDF/UA",
        "per_check": agg("check"),
        "per_profile": agg("profile"),
        "per_fixture": agg("fixture"),
        "structure_fixture_matrix": matrix,
        "first_failures": [r for r in rows if not r["pass"]][:40],
        "rows": rows,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, default=str)
    print(f"structure: {passed}/{len(rows)} checks pass")


if __name__ == "__main__":
    main()

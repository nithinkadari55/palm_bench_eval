#!/usr/bin/env python3
"""Validate every generated fixture against the flavour(s) its profile claims, plus negative controls."""
import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

BATCH = 25


def run_verapdf(verapdf, flavour, files, fmt):
    cmd = [verapdf, "--flavour", flavour, "--format", fmt, "--maxfailuresdisplayed", "3"] + files
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    return p.returncode, p.stdout, p.stderr


def _rules_from_json(details):
    rules = []
    for r in details.get("ruleSummaries", []) or []:
        status = (r.get("ruleStatus") or r.get("status") or "").upper()
        if status == "FAILED":
            rules.append({
                "specification": r.get("specification"), "clause": r.get("clause"), "test": r.get("testNumber"),
                "failed_checks": r.get("failedChecks"), "description": (r.get("description") or "")[:240],
                "object": r.get("object"),
            })
    return rules


def parse_json(text):
    """Returns {abs_path: {compliant, profile, failed_rules[], passed_rules, failed_rules_count, error}}."""
    out = {}
    doc = json.loads(text)
    jobs = doc.get("report", doc).get("jobs", [])
    for job in jobs:
        name = os.path.abspath((job.get("itemDetails") or {}).get("name", ""))
        vr = job.get("validationResult")
        if vr is None:
            out[name] = {"compliant": None, "error": json.dumps(job.get("taskResult") or job.get("taskException") or job)[:800]}
            continue
        if isinstance(vr, dict):
            vr = [vr]
        if not vr:
            out[name] = {"compliant": None, "error": "empty validationResult"}
            continue
        v = vr[0]
        details = v.get("details") or {}
        compliant = v.get("compliant", v.get("isCompliant"))
        out[name] = {
            "compliant": bool(compliant) if compliant is not None else None,
            "profile": v.get("profileName"),
            "statement": v.get("statement"),
            "passed_rules": details.get("passedRules"),
            "failed_rules_count": details.get("failedRules"),
            "failed_checks": details.get("failedChecks"),
            "failed_rules": _rules_from_json(details),
            "job_end_status": v.get("jobEndStatus"),
        }
    return out


def parse_xml(text):
    out = {}
    root = ET.fromstring(text)
    for job in root.iter("job"):
        item = job.find("item")
        name = os.path.abspath(item.findtext("name") if item is not None else "")
        rep = job.find("validationReport")
        if rep is None:
            out[name] = {"compliant": None, "error": ET.tostring(job, encoding="unicode")[:800]}
            continue
        det = rep.find("details")
        rules = []
        if det is not None:
            for r in det.iter("rule"):
                if (r.get("status") or "").lower() == "failed":
                    rules.append({"specification": r.get("specification"), "clause": r.get("clause"), "test": r.get("testNumber"),
                                  "failed_checks": r.get("failedChecks"), "description": (r.findtext("description") or "")[:240]})
        out[name] = {
            "compliant": rep.get("isCompliant") == "true",
            "profile": rep.get("profileName"),
            "statement": rep.get("statement"),
            "passed_rules": det.get("passedRules") if det is not None else None,
            "failed_rules_count": det.get("failedRules") if det is not None else None,
            "failed_rules": rules,
            "job_end_status": rep.get("jobEndStatus"),
        }
    return out


def validate(verapdf, flavour, files, raw_dir):
    results = {}
    for i in range(0, len(files), BATCH):
        batch = files[i:i + BATCH]
        rc, out, err = run_verapdf(verapdf, flavour, batch, "json")
        parsed = {}
        try:
            parsed = parse_json(out)
        except Exception as e:
            sys.stderr.write(f"JSON parse failed for flavour {flavour}: {e!r}; retrying with XML\n")
        if not parsed:
            rc, out, err = run_verapdf(verapdf, flavour, batch, "xml")
            try:
                parsed = parse_xml(out)
            except Exception as e:
                parsed = {}
                sys.stderr.write(f"XML parse failed: {e!r}\n{err[:2000]}\n")
        if raw_dir:
            with open(os.path.join(raw_dir, f"{flavour}_{i // BATCH:03d}.txt"), "w", encoding="utf-8") as f:
                f.write(out[:2_000_000])
        for fpath in batch:
            results[os.path.abspath(fpath)] = parsed.get(os.path.abspath(fpath), {"compliant": None, "error": f"no result (rc={rc}) {err[-600:]}"})
    return results


# ---------------------------------------------------------------- negative controls

def patch_pdfa_part(src, dst, old_part, new_part):
    data = open(src, "rb").read()
    pats = [
        (f"<pdfaid:part>{old_part}</pdfaid:part>".encode(), f"<pdfaid:part>{new_part}</pdfaid:part>".encode()),
        (f'pdfaid:part="{old_part}"'.encode(), f'pdfaid:part="{new_part}"'.encode()),
    ]
    for a, b in pats:
        if a in data:
            open(dst, "wb").write(data.replace(a, b))
            return True
    return False


def strip_with_pikepdf(src, dst, what):
    import pikepdf
    with pikepdf.open(src) as pdf:
        if what == "tounicode":
            n = 0
            for page in pdf.pages:
                fonts = page.obj.get("/Resources", {}).get("/Font", {})
                for _, f in fonts.items():
                    if "/ToUnicode" in f:
                        del f["/ToUnicode"]
                        n += 1
            if n == 0:
                return False
        elif what == "structtree":
            root = pdf.Root
            for k in ("/StructTreeRoot", "/MarkInfo"):
                if k in root:
                    del root[k]
            for page in pdf.pages:
                if "/StructParents" in page.obj:
                    del page.obj["/StructParents"]
        pdf.save(dst, deterministic_id=True)
    return True


def controls(corpus, file_of, work):
    os.makedirs(work, exist_ok=True)
    defs = [
        {"id": "a1b_claim_with_transparency", "flavour": "1b", "expect_clause": "6.4",
         "why": "PDF/A-2b output of vector_transparency with its XMP part patched 2 -> 1; PDF/A-1 forbids transparency",
         "make": lambda dst: patch_pdfa_part(file_of("vector_transparency", "a2b"), dst, 2, 1)},
        {"id": "plain_pdf_validated_as_2b", "flavour": "2b", "expect_clause": "6.6.",
         "why": "profile=none output (no PDF/A identification, no OutputIntent) validated as PDF/A-2b",
         "make": lambda dst: _copy(file_of("vector_opaque", "none"), dst)},
        {"id": "a2u_without_tounicode", "flavour": "2u", "expect_clause": "6.2.11.7",
         "why": "PDF/A-2u text fixture with every /ToUnicode CMap removed",
         "make": lambda dst: strip_with_pikepdf(file_of("text", "a2u"), dst, "tounicode")},
        {"id": "ua1_without_structure_tree", "flavour": "ua1", "expect_clause": "",
         "why": "PDF/UA-1 structure fixture with /StructTreeRoot and /MarkInfo deleted",
         "make": lambda dst: strip_with_pikepdf(file_of("structure", "ua1"), dst, "structtree")},
        {"id": "a4_claim_on_pdf17", "flavour": "4", "expect_clause": "6.1.",
         "why": "PDF/A-2b (PDF 1.7) output with XMP part patched 2 -> 4; PDF/A-4 requires a PDF 2.0 header",
         "make": lambda dst: patch_pdfa_part(file_of("vector_opaque", "a2b"), dst, 2, 4)},
        {"id": "a2b_claim_with_non_pdfa_attachment", "flavour": "2b", "expect_clause": "6.8",
         "why": "PDF/A-3b embedded_file output patched 3 -> 2; PDF/A-2 only allows PDF/A attachments",
         "make": lambda dst: patch_pdfa_part(file_of("embedded_file", "a3b"), dst, 3, 2)},
    ]
    out = []
    for d in defs:
        dst = os.path.join(work, d["id"] + ".pdf")
        try:
            ok = d["make"](dst)
        except FileNotFoundError as e:
            ok, err = False, f"source missing: {e}"
        except Exception as e:
            ok, err = False, repr(e)
        else:
            err = None if ok else "patch target not found"
        out.append({"id": d["id"], "flavour": d["flavour"], "expect_clause": d["expect_clause"], "why": d["why"],
                    "path": dst if ok else None, "build_error": err})
    return out


def _copy(src, dst):
    with open(src, "rb") as f, open(dst, "wb") as g:
        g.write(f.read())
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--verapdf", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    profiles = {p["id"]: p for p in gen["profiles"]}
    ver = subprocess.run([args.verapdf, "--version"], capture_output=True, text=True).stdout.strip()
    raw_dir = os.path.join(args.work, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    def file_of(fixture, profile):
        p = os.path.join(args.corpus, fixture, profiles[profile]["file_id"] + ".pdf")
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        return p

    by_flavour = {}
    for e in gen["entries"]:
        prof = profiles[e["profile"]]
        for fl in prof["verapdf"]:
            if e["status"] == "ok":
                by_flavour.setdefault(fl, []).append((e, os.path.abspath(os.path.join(args.corpus, e["file"]))))
    rows = []
    for fl, items in sorted(by_flavour.items()):
        res = validate(args.verapdf, fl, [p for _, p in items], raw_dir)
        for e, p in items:
            r = res.get(p, {})
            rows.append({"fixture": e["fixture"], "profile": e["profile"], "flavour": fl, **r})

    # matrix: profile x fixture
    matrix = {}
    for e in gen["entries"]:
        prof = profiles[e["profile"]]
        if not prof["verapdf"]:
            continue
        cell = matrix.setdefault(e["profile"], {})
        if e["status"] != "ok":
            cell[e["fixture"]] = "refused" if e["status"] == "refused" else e["status"]
            continue
        rs = [r for r in rows if r["fixture"] == e["fixture"] and r["profile"] == e["profile"]]
        if any(r.get("compliant") is None for r in rs):
            cell[e["fixture"]] = "error"
        elif all(r.get("compliant") for r in rs):
            cell[e["fixture"]] = "pass"
        else:
            cell[e["fixture"]] = "fail"

    ctrl = controls(args.corpus, file_of, os.path.join(args.work, "controls"))
    for c in ctrl:
        if not c["path"]:
            c["result"] = "skipped"
            continue
        r = validate(args.verapdf, c["flavour"], [os.path.abspath(c["path"])], None).get(os.path.abspath(c["path"]), {})
        c["compliant"] = r.get("compliant")
        c["failed_rules"] = r.get("failed_rules", [])[:10]
        c["error"] = r.get("error")
        hit = any((fr.get("clause") or "").startswith(c["expect_clause"]) for fr in c["failed_rules"]) if c["expect_clause"] else bool(c["failed_rules"])
        c["expected_rule_hit"] = hit
        c["result"] = "pass" if r.get("compliant") is False else ("fail" if r.get("compliant") else "error")

    pos = [r for r in rows]
    passed = sum(1 for r in pos if r.get("compliant") is True)
    neg_pass = sum(1 for c in ctrl if c["result"] == "pass")
    neg_total = sum(1 for c in ctrl if c["result"] != "skipped")
    total = len(pos) + neg_total
    fails = [r for r in pos if r.get("compliant") is not True]
    rule_counts = {}
    for r in fails:
        for fr in r.get("failed_rules", []):
            k = f"{fr.get('specification')} {fr.get('clause')}-{fr.get('test')}"
            rule_counts[k] = rule_counts.get(k, 0) + 1
    result = {
        "test": f"verapdf_{args.label}",
        "verapdf_version": ver,
        "pass": passed + neg_pass, "fail": total - passed - neg_pass, "total": total,
        "pass_rate": (passed + neg_pass) / total if total else None,
        "pass_criterion": "positive: veraPDF reports compliant for the flavour the profile claims (combined profiles must pass every flavour); negative control: veraPDF reports non-compliant",
        "positive": {"pass": passed, "total": len(pos)},
        "negative_controls": {"pass": neg_pass, "total": neg_total, "controls": ctrl},
        "matrix": matrix,
        "failed_rule_counts": dict(sorted(rule_counts.items(), key=lambda kv: -kv[1])),
        "results": rows,
        "first_failures": [{k: r.get(k) for k in ("fixture", "profile", "flavour", "compliant", "error", "failed_rules")} for r in fails[:20]],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(f"veraPDF {ver}: positive {passed}/{len(pos)}, negative controls {neg_pass}/{neg_total}")


if __name__ == "__main__":
    main()

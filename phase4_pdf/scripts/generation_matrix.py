#!/usr/bin/env python3
"""Turns corpus/generation.json into the profile x fixture acceptance matrix with krilla's refusal reasons."""
import argparse
import json
import os
import re


def short(err):
    m = re.match(r"([A-Za-z]+)(\((\w+))?", err)
    if not m:
        return err[:60]
    arg = m.group(3)
    keep = arg and arg[0].isupper() and arg not in ("None", "Some", "Font")
    by = re.search(r"\[([^\]]+)\]\s*$", err)
    return m.group(1) + (f"({arg})" if keep else "") + (f" [{by.group(1)}]" if by else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    gen = json.load(open(os.path.join(args.corpus, "generation.json"), encoding="utf-8"))
    manifest = json.load(open(args.manifest, encoding="utf-8"))
    matrix, reasons = {}, {}
    for e in gen["entries"]:
        cell = e["status"]
        if e["status"] == "refused":
            kinds = sorted({short(x) for x in e.get("errors", [])})
            cell = "refused: " + ", ".join(kinds)
            for k in kinds:
                reasons.setdefault(k, set()).add(f"{e['fixture']}@{e['profile']}")
        elif e["status"] in ("error", "panic", "asset_error", "config_invalid"):
            cell = f"{e['status']}: {(e.get('errors') or [''])[0][:160]}"
        matrix.setdefault(e["profile"], {})[e["fixture"]] = cell
    ok_states = ("ok", "refused", "config_invalid")
    passed = sum(e["status"] in ok_states for e in gen["entries"])
    total = len(gen["entries"])
    result = {
        "test": f"generation_{args.label}",
        "krilla_version": gen["krilla_version"],
        "pass": passed, "fail": total - passed, "total": total,
        "pass_rate": passed / total if total else None,
        "pass_criterion": "krilla either writes the PDF or refuses it with KrillaError::Validation (a refusal is the documented contract for content the profile forbids); a panic, a non-validation KrillaError or a missing asset fails",
        "status_counts": {s: sum(e["status"] == s for e in gen["entries"]) for s in sorted({e["status"] for e in gen["entries"]})},
        "profiles": gen["profiles"],
        "profiles_not_offered": gen["profiles_not_offered"],
        "unsupported_features": gen["unsupported_features"],
        "matrix": matrix,
        "refusal_reasons": {k: sorted(v) for k, v in sorted(reasons.items())},
        "assets": {"manifest_font_errors": manifest.get("font_errors"), "cmyk_icc": manifest.get("cmyk_icc_info"), **gen.get("assets", {})},
        "entries": gen["entries"],
        "first_failures": [e for e in gen["entries"] if e["status"] not in ok_states][:20],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(json.dumps(result["status_counts"]))


if __name__ == "__main__":
    main()

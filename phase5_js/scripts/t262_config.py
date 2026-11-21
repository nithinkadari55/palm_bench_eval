#!/usr/bin/env python3
"""Turn QuickJS-NG's test262.conf (vendored in rquickjs-sys 0.14.0) into the JSON config
read by the Rust harness. Both engines use the same config, so the skip list is the one
QuickJS-NG itself uses at that commit.

[features]  name=skip  -> skip_features
[exclude]   path       -> exclude_paths / exclude_prefixes ("!path" re-includes)
"""
import argparse
import json
import sys

# Features the harness cannot provide the host hooks for (counted separately as "harness:").
HARNESS_UNSUPPORTED = ["IsHTMLDDA", "cross-realm", "import-text", "import-bytes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout-ms", type=int, default=10000)
    a = ap.parse_args()
    section = None
    skip, ex_paths, ex_prefixes, inc_prefixes, features_seen = [], [], [], [], []
    for raw in open(a.conf, encoding="utf-8"):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section == "features":
            name, _, val = line.partition("=")
            name, val = name.strip(), val.strip()
            features_seen.append(name)
            if val == "skip":
                skip.append(name)
        elif section == "exclude":
            neg = line.startswith("!")
            p = line[1:] if neg else line
            if p.startswith("test262/"):
                p = p[len("test262/"):]
            if neg:
                inc_prefixes.append(p)
            elif p.endswith("/"):
                ex_prefixes.append(p)
            else:
                ex_paths.append(p)
    cfg = {
        "test262_commit": a.commit,
        "source": "quickjs-ng test262.conf vendored in rquickjs-sys 0.14.0 (quickjs-ng 0fdea21)",
        "skip_features": sorted(skip),
        "harness_unsupported_features": HARNESS_UNSUPPORTED,
        "exclude_paths": sorted(ex_paths),
        "exclude_prefixes": ex_prefixes,
        "include_prefixes": inc_prefixes,
        "features_listed": len(features_seen),
        "timeout_ms": a.timeout_ms,
    }
    json.dump(cfg, open(a.out, "w", encoding="utf-8"), indent=2)
    print(f"skip_features={len(skip)} exclude_paths={len(ex_paths)} exclude_prefixes={ex_prefixes} include_prefixes={inc_prefixes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

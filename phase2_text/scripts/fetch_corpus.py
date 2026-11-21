#!/usr/bin/env python3
import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

UDHR_COMMIT = "e6a1b6f8cb048fba115d6b81bab47875a4eca0d8"
UDHR_BASE = f"https://raw.githubusercontent.com/eric-muller/udhr/{UDHR_COMMIT}/data/udhr/"
EMOJI_VERSION = "16.0"
EMOJI_ZWJ_URL = f"https://www.unicode.org/Public/emoji/{EMOJI_VERSION}/emoji-zwj-sequences.txt"
LINES_PER_LANGUAGE = 50
EMOJI_PER_LINE = 10

LANGUAGES = [
    ("latin", "eng", "en", "Latn", "ltr"),
    ("latin", "fra", "fr", "Latn", "ltr"),
    ("latin", "deu_1996", "de", "Latn", "ltr"),
    ("latin", "vie", "vi", "Latn", "ltr"),
    ("arabic", "arb", "ar", "Arab", "rtl"),
    ("arabic", "pes_1", "fa", "Arab", "rtl"),
    ("arabic", "urd", "ur", "Arab", "rtl"),
    ("hebrew", "heb", "he", "Hebr", "rtl"),
    ("devanagari", "hin", "hi", "Deva", "ltr"),
    ("bengali", "ben", "bn", "Beng", "ltr"),
    ("tamil", "tam", "ta", "Taml", "ltr"),
    ("telugu", "tel", "te", "Telu", "ltr"),
    ("gujarati", "guj", "gu", "Gujr", "ltr"),
    ("thai", "tha", "th", "Thai", "ltr"),
    ("khmer", "khm", "km", "Khmr", "ltr"),
    ("myanmar", "mya", "my", "Mymr", "ltr"),
    ("sinhala", "sin", "si", "Sinh", "ltr"),
    ("cjk", "cmn_hans", "zh-Hans", "Hani", "ltr"),
    ("cjk", "cmn_hant", "zh-Hant", "Hani", "ltr"),
    ("cjk", "jpn", "ja", "Hani", "ltr"),
    ("hangul", "kor", "ko", "Hang", "ltr"),
]

NS = "{http://efele.net/udhr}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "phase2-text-eval"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def udhr_lines(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if el.tag in (NS + "title", NS + "para"):
            text = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
            if text:
                out.append(text)
        if len(out) >= LINES_PER_LANGUAGE:
            break
    return out


def emoji_sequences(txt):
    seqs = []
    for line in txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        cps = line.split(";", 1)[0].split()
        seqs.append("".join(chr(int(c, 16)) for c in cps))
    return seqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    entries = []
    for group, f, lang, script, direction in LANGUAGES:
        url = UDHR_BASE + f"udhr_{f}.xml"
        lines = udhr_lines(fetch(url))
        if len(lines) < LINES_PER_LANGUAGE:
            print(f"warning: {f} has only {len(lines)} lines", file=sys.stderr)
        entries.append({
            "id": f, "group": group, "lang": lang, "script": script,
            "direction": direction, "source": url, "kind": "udhr", "lines": lines,
        })
    seqs = emoji_sequences(fetch(EMOJI_ZWJ_URL).decode("utf-8"))
    grouped = [" ".join(seqs[i:i + EMOJI_PER_LINE]) for i in range(0, len(seqs), EMOJI_PER_LINE)]
    entries.append({
        "id": "emoji_zwj", "group": "emoji", "lang": "en", "script": "Zyyy",
        "direction": "ltr", "source": EMOJI_ZWJ_URL, "kind": "emoji",
        "lines": grouped, "sequences": seqs,
    })
    corpus = {
        "sources": {
            "udhr": {"repo": "https://github.com/eric-muller/udhr", "commit": UDHR_COMMIT,
                     "license": "UDHR text: United Nations (OHCHR) translations; XML markup: UDHR in XML project; no LICENSE file in repository; used for CI-only testing, not redistributed"},
            "emoji": {"url": EMOJI_ZWJ_URL, "license": "Unicode License v3 (https://www.unicode.org/license.txt)"},
        },
        "lines_per_language": LINES_PER_LANGUAGE,
        "entries": entries,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, ensure_ascii=False, indent=1)
    for e in entries:
        print(e["id"], len(e["lines"]))


if __name__ == "__main__":
    main()

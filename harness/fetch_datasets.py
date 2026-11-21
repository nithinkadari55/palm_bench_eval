import argparse
import json
import os
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "bench-harness/1.0"}


def get(url, binary=False, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def design2code(out, n):
    os.makedirs(out, exist_ok=True)
    meta = json.loads(get("https://huggingface.co/api/datasets/SALT-NLP/Design2Code"))
    names = sorted({s["rfilename"][:-5] for s in meta["siblings"] if s["rfilename"].endswith(".html")}, key=lambda x: int(x) if x.isdigit() else x)
    step = max(1, len(names) // n)
    picked = names[::step][:n]
    got = []
    for nm in picked:
        try:
            html = get(f"https://huggingface.co/datasets/SALT-NLP/Design2Code/resolve/main/{nm}.html")
            png = get(f"https://huggingface.co/datasets/SALT-NLP/Design2Code/resolve/main/{nm}.png", binary=True)
        except Exception as e:  # noqa: BLE001
            print("skip", nm, e)
            continue
        with open(os.path.join(out, f"d2c_{nm}.html"), "w", encoding="utf-8") as f:
            f.write(html)
        with open(os.path.join(out, f"d2c_{nm}.png"), "wb") as f:
            f.write(png)
        got.append(f"d2c_{nm}")
    return {"dataset": "SALT-NLP/Design2Code", "license": "ODC-BY", "total_available": len(names), "picked": got}


def websight(out, n):
    os.makedirs(out, exist_ok=True)
    got = []
    offset = 0
    stride = 997
    while len(got) < n:
        url = ("https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
            {"dataset": "HuggingFaceM4/WebSight", "config": "v0.1", "split": "train", "offset": offset, "length": 1}))
        try:
            j = json.loads(get(url))
            row = j["rows"][0]["row"]
            png = get(row["image"]["src"], binary=True)
        except Exception as e:  # noqa: BLE001
            print("skip websight", offset, e)
            offset += stride
            continue
        nm = f"ws_{offset:07d}"
        with open(os.path.join(out, nm + ".html"), "w", encoding="utf-8") as f:
            f.write(row["text"])
        with open(os.path.join(out, nm + ".png"), "wb") as f:
            f.write(png)
        got.append(nm)
        offset += stride
    return {"dataset": "HuggingFaceM4/WebSight v0.1", "license": "CC-BY-4.0", "picked": got}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--d2c", type=int, default=120)
    ap.add_argument("--websight", type=int, default=120)
    a = ap.parse_args()
    man = {"design2code": design2code(a.out, a.d2c), "websight": websight(a.out, a.websight)}
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print(json.dumps({k: len(v["picked"]) for k, v in man.items()}))


if __name__ == "__main__":
    main()

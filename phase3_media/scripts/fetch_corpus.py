#!/usr/bin/env python3
"""Download the pinned test corpora (see SOURCES.md). Usage: fetch_corpus.py --data DIR NAME [NAME...]"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

GIT = {
    "libjpeg-turbo": ("https://github.com/libjpeg-turbo/libjpeg-turbo.git",
                      "7b4993786d856cbccabfc0ed2f923ba000e326cc", ["/testimages/*"]),
    "libwebp-test-data": ("https://github.com/webmproject/libwebp-test-data.git",
                          "06ddd96e276c2c638a72d39d3c0f340afd61978c", ["/*"]),
    "pygif": ("https://github.com/robert-ancell/pygif.git",
              "741b282047e0dde112e5ac2df0c7f8f923cb5df6", ["/test-suite/*"]),
    "image-gif": ("https://github.com/image-rs/image-gif.git",
                  "a5f89ddc2b29424334244c97456b4a26e208aa7d", ["/tests/samples/*"]),
    "avif-link-u": ("https://github.com/link-u/avif-sample-images.git",
                    "c666a368b73006246694919b5dbcc078317af6cc", ["/*.avif", "/*.avifs", "/README.md", "/LICENSE.txt"]),
    "av1-avif": ("https://github.com/AOMediaCodec/av1-avif.git",
                 "bf4c18d1f3971069b75e87d6ee469790589f4f09",
                 ["/testFiles/Microsoft/*.avif", "/testFiles/Apple/**/*.avif", "/testFiles/Netflix/avif/*.avif",
                  "/testFiles/Netflix/avis/*.avif", "/testFiles/Xiph/*.avif", "/testFiles/*/license.txt",
                  "/testFiles/*/LICENSE*", "/testFiles/*/COPYING", "/testFiles/Microsoft/ReadMe.md"]),
    "exif-orientation": ("https://github.com/recurser/exif-orientation-examples.git",
                         "219294e144531b0c01247913cb58b6f5531b5081", ["/*.jpg", "/LICENSE"]),
    "compact-icc": ("https://github.com/saucecontrol/Compact-ICC-Profiles.git",
                    "bdd84663061bc4ae95ca70decff54f581e27f702", ["/profiles/*", "/license"]),
    "wpt-css-color": ("https://github.com/web-platform-tests/wpt.git",
                      "9986bb32c9e97707eff870ab284ebc5cc7ae8d21", ["/css/css-color/parsing/*"]),
    "resvg-tests-0.45.1": ("https://github.com/linebender/resvg.git",
                           "1b6c2fddbcbeffa8135df4323b02aaae84890907",
                           ["/crates/resvg/tests/*", "/crates/resvg/tests/**"]),
}

TARBALLS = {
    "pngsuite": ("http://www.schaik.com/pngsuite/PngSuite-2017jul19.tgz",
                 "0294b244c95a8342c01b00010cf34abdcabc7c6a34fd0fe1bd963917537bfdc8"),
}

FILES = {
    "cmyk-jpeg": [
        ("jpeg-decoder_ycck.jpg", "https://raw.githubusercontent.com/image-rs/jpeg-decoder/eb2d7c0f6a2d0298aba7a7f8b9ca1440353e8f8c/tests/reftest/images/ycck.jpg"),
        ("mozilla_jpg-cmyk-1.jpg", "https://raw.githubusercontent.com/image-rs/jpeg-decoder/eb2d7c0f6a2d0298aba7a7f8b9ca1440353e8f8c/tests/reftest/images/mozilla/jpg-cmyk-1.jpg"),
        ("mozilla_jpg-cmyk-2.jpg", "https://raw.githubusercontent.com/image-rs/jpeg-decoder/eb2d7c0f6a2d0298aba7a7f8b9ca1440353e8f8c/tests/reftest/images/mozilla/jpg-cmyk-2.jpg"),
        ("jpeg-js_tree-cmyk.jpg", "https://raw.githubusercontent.com/jpeg-js/jpeg-js/1031ccd7a63c641c16afb2430279d1598530a85c/test/fixtures/tree-cmyk.jpg"),
        ("jpeg-js_tree-cmyk-notransform.jpg", "https://raw.githubusercontent.com/jpeg-js/jpeg-js/1031ccd7a63c641c16afb2430279d1598530a85c/test/fixtures/tree-cmyk-notransform.jpg"),
        ("jpeg-js_cmyktest.jpg", "https://raw.githubusercontent.com/jpeg-js/jpeg-js/1031ccd7a63c641c16afb2430279d1598530a85c/test/fixtures/cmyktest.jpg"),
        ("jpeg-js_cmyk-grey.jpg", "https://raw.githubusercontent.com/jpeg-js/jpeg-js/1031ccd7a63c641c16afb2430279d1598530a85c/test/fixtures/cmyk-grey.jpg"),
        ("jpeg-js_plusshelf-drawing.jpg", "https://raw.githubusercontent.com/jpeg-js/jpeg-js/1031ccd7a63c641c16afb2430279d1598530a85c/test/fixtures/plusshelf-drawing.jpg"),
        ("pillow_pil_sample_cmyk.jpg", "https://raw.githubusercontent.com/python-pillow/Pillow/5cdbe88ccc3db2067235f6c22d553abb61654997/Tests/images/pil_sample_cmyk.jpg"),
        ("zune_baseline_cmyk.jpg", "https://raw.githubusercontent.com/etemesi254/zune-image/692520ae7b6fb2098a25c7ee92521eda5b4425a9/test-images/jpeg/app14/baseline_cmyk.jpg"),
    ],
    "icc-real": [
        ("pillow_xmp_test_adobergb.jpg", "https://raw.githubusercontent.com/python-pillow/Pillow/5cdbe88ccc3db2067235f6c22d553abb61654997/Tests/images/xmp_test.jpg"),
    ],
}


def run(cmd, **kw):
    print("+", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True, **kw)


def git_sparse(name, dest):
    url, sha, patterns = GIT[name]
    if os.path.isdir(os.path.join(dest, ".git")):
        head = subprocess.run(["git", "-C", dest, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head == sha:
            return {"name": name, "url": url, "sha": sha, "cached": True}
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    run(["git", "init", "-q", dest])
    run(["git", "-C", dest, "remote", "add", "origin", url])
    run(["git", "-C", dest, "sparse-checkout", "set", "--no-cone"] + patterns)
    for attempt in range(4):
        try:
            run(["git", "-C", dest, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", sha])
            break
        except subprocess.CalledProcessError:
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))
    run(["git", "-C", dest, "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD"])
    head = subprocess.run(["git", "-C", dest, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != sha:
        raise SystemExit(f"{name}: HEAD {head} != pinned {sha}")
    return {"name": name, "url": url, "sha": sha}


def download(url, path):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "phase3-media-eval"})
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as fh:
                shutil.copyfileobj(r, fh)
            return
        except Exception as e:  # noqa: BLE001
            if attempt == 4:
                raise
            print(f"retry {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def fetch_tarball(name, dest):
    url, want = TARBALLS[name]
    os.makedirs(dest, exist_ok=True)
    tgz = os.path.join(dest, os.path.basename(url))
    if not os.path.exists(tgz) or sha256(tgz) != want:
        download(url, tgz)
    got = sha256(tgz)
    if got != want:
        raise SystemExit(f"{name}: sha256 {got} != {want}")
    with tarfile.open(tgz) as t:
        for m in t.getmembers():
            if not m.isfile() or m.name.startswith("/") or ".." in m.name:
                continue
            m.name = os.path.basename(m.name)
            t.extract(m, dest)
    return {"name": name, "url": url, "sha256": want}


def fetch_files(name, dest):
    os.makedirs(dest, exist_ok=True)
    out = []
    for fname, url in FILES[name]:
        p = os.path.join(dest, fname)
        if not os.path.exists(p):
            download(url, p)
        out.append({"file": fname, "url": url, "sha256": sha256(p)})
    return {"name": name, "files": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("names", nargs="+")
    args = ap.parse_args()
    os.makedirs(args.data, exist_ok=True)
    records = []
    for n in args.names:
        dest = os.path.join(args.data, n)
        if n in GIT:
            records.append(git_sparse(n, dest))
        elif n in TARBALLS:
            records.append(fetch_tarball(n, dest))
        elif n in FILES:
            records.append(fetch_files(n, dest))
        else:
            raise SystemExit(f"unknown corpus {n}")
    with open(os.path.join(args.data, "corpus-" + "-".join(args.names)[:80] + ".json"), "w") as fh:
        json.dump(records, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Locate the system fonts, synthesise the raster images and write the asset manifest read by `gen` and `robust`."""
import argparse
import hashlib
import json
import os
import struct
import sys
import zlib

from fontTools.ttLib import TTCollection, TTFont
from PIL import Image, ImageDraw

FONT_DIRS = ["/usr/share/fonts"]

# role -> (candidate file names, family name for TTC face selection or None)
FONT_ROLES = {
    "latin": (["NotoSans-Regular.ttf"], None),
    "latin_lig": (["DejaVuSans.ttf"], None),
    "arabic": (["NotoSansArabic-Regular.ttf", "NotoNaskhArabic-Regular.ttf"], None),
    "devanagari": (["NotoSansDevanagari-Regular.ttf"], None),
    "cjk_sc": (["NotoSansCJK-Regular.ttc"], "Noto Sans CJK SC"),
    "cjk_jp": (["NotoSansCJK-Regular.ttc"], "Noto Sans CJK JP"),
    "cjk_kr": (["NotoSansCJK-Regular.ttc"], "Noto Sans CJK KR"),
    "emoji_cbdt": (["NotoColorEmoji.ttf"], None),
    "variable": (["InterVariable.ttf", "Inter[opsz,wght].ttf", "Inter-VariableFont_opsz,wght.ttf"], None),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_file(names):
    for root in FONT_DIRS:
        for dirpath, _, files in os.walk(root):
            for n in names:
                if n in files:
                    return os.path.join(dirpath, n)
    return None


def family_names(font):
    out = set()
    for rec in font["name"].names:
        if rec.nameID in (1, 16):
            try:
                out.add(rec.toUnicode())
            except Exception:
                pass
    return out


def font_info(path, index, family):
    info = {"path": path, "index": index, "bytes": os.path.getsize(path), "sha256": sha256(path)}
    if path.lower().endswith(".ttc"):
        coll = TTCollection(path, lazy=True)
        if family:
            for i, f in enumerate(coll.fonts):
                if family in family_names(f):
                    index = i
                    break
            else:
                raise RuntimeError(f"family {family} not in {path}")
        font = coll.fonts[index]
        info["index"] = index
    else:
        font = TTFont(path, lazy=True)
    info["postscript_name"] = font["name"].getDebugName(6)
    info["family"] = sorted(family_names(font))
    info["num_glyphs"] = font["maxp"].numGlyphs
    info["tables"] = sorted(font.keys())
    info["outline_format"] = "CFF" if ("CFF " in font or "CFF2" in font) else ("glyf" if "glyf" in font else "none")
    info["color_tables"] = [t for t in ("COLR", "CPAL", "CBDT", "sbix", "SVG ") if t in font]
    info["variable_axes"] = [a.axisTag for a in font["fvar"].axes] if "fvar" in font else []
    info["fsType"] = font["OS/2"].fsType if "OS/2" in font else None
    return info


def write_png(path, width, height, bit_depth, color_type, row_fn):
    """Minimal streaming PNG writer (filter 0) so 16-bit RGB and 16k x 16k images need no big buffers."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    comp = zlib.compressobj(6)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)))
        idat = bytearray()
        for y in range(height):
            idat += comp.compress(b"\x00" + row_fn(y))
            if len(idat) > (1 << 22):
                f.write(chunk(b"IDAT", bytes(idat)))
                idat = bytearray()
        idat += comp.flush()
        f.write(chunk(b"IDAT", bytes(idat)))
        f.write(chunk(b"IEND", b""))


def colour_bars(w, h):
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    cols = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
    bw = w // len(cols)
    for i, c in enumerate(cols):
        d.rectangle([i * bw, 0, (i + 1) * bw - 1, int(h * 0.7)], fill=c)
    for x in range(w):
        g = int(255 * x / (w - 1))
        d.line([x, int(h * 0.7) + 1, x, h - 1], fill=(g, g, g))
    return img


def make_images(out):
    os.makedirs(out, exist_ok=True)
    paths = {}
    bars = colour_bars(320, 200)
    p = os.path.join(out, "rgb.png"); bars.save(p, optimize=False); paths["rgb_png"] = p
    gray = Image.linear_gradient("L").resize((256, 64))
    p = os.path.join(out, "gray.png"); gray.save(p); paths["gray_png"] = p
    rgba = bars.convert("RGBA")
    alpha = Image.linear_gradient("L").rotate(90).resize(rgba.size)
    rgba.putalpha(alpha)
    p = os.path.join(out, "rgba.png"); rgba.save(p); paths["rgba_png"] = p
    p = os.path.join(out, "photo.jpg"); bars.save(p, quality=90); paths["jpeg_rgb"] = p
    cmyk = Image.new("CMYK", (320, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(cmyk)
    for i, c in enumerate([(255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0), (0, 0, 0, 255)]):
        d.rectangle([i * 80, 0, i * 80 + 79, 199], fill=c)
    p = os.path.join(out, "cmyk.jpg"); cmyk.save(p, quality=90); paths["jpeg_cmyk"] = p

    def rgb16_row(y, w=256):
        row = bytearray()
        for x in range(w):
            row += struct.pack(">HHH", x * 257, y * 257 * 4 % 65536, 65535 - x * 257)
        return bytes(row)
    p = os.path.join(out, "rgb16.png"); write_png(p, 256, 64, 16, 2, rgb16_row); paths["rgb16_png"] = p

    n = 16384
    tiles = [bytes(((x // 256 + t) % 2) * 255 for x in range(n)) for t in (0, 1)]
    p = os.path.join(out, "big16k.png"); write_png(p, n, n, 8, 0, lambda y: tiles[(y // 256) % 2]); paths["png_16k"] = p
    return paths


def find_cmyk_icc():
    for p in ["/usr/share/color/icc/colord/FOGRA39L_coated.icc", "/usr/share/color/icc/colord/SWOP_TR005_coated_5.icc"]:
        if os.path.exists(p):
            with open(p, "rb") as f:
                head = f.read(128)
            if head[16:20] == b"CMYK":
                return p, {"path": p, "sha256": sha256(p), "icc_version": f"{head[8]}.{head[9] >> 4}.{head[9] & 15}", "colour_space": "CMYK"}
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--colrv1", required=True, help="path to Noto-COLRv1.ttf")
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    fonts, errors = {}, {}
    for role, (names, family) in FONT_ROLES.items():
        path = find_file(names)
        if not path:
            errors[role] = f"none of {names} under {FONT_DIRS}"
            continue
        try:
            fonts[role] = font_info(path, 0, family)
        except Exception as e:
            errors[role] = repr(e)
    if os.path.exists(args.colrv1):
        try:
            fonts["emoji_colrv1"] = font_info(args.colrv1, 0, None)
        except Exception as e:
            errors["emoji_colrv1"] = repr(e)
    else:
        errors["emoji_colrv1"] = f"missing {args.colrv1}"
    images = make_images(os.path.join(args.out, "images"))
    xml = os.path.join(args.out, "data.xml")
    with open(xml, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<invoice id="phase4"><line sku="A-1" qty="3"/><line sku="B-2" qty="5"/></invoice>\n')
    icc_path, icc_info = find_cmyk_icc()
    manifest = {
        "fonts": fonts,
        "font_errors": errors,
        "images": images,
        "files": {"embed_xml": xml},
        "cmyk_icc": icc_path,
        "cmyk_icc_info": icc_info,
    }
    with open(args.manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps({"fonts": {k: v["path"] + f"#{v['index']}" for k, v in fonts.items()}, "font_errors": errors, "cmyk_icc": icc_info}, indent=2))
    if errors:
        print("WARNING: some font roles are missing; dependent fixtures will report asset_error", file=sys.stderr)


if __name__ == "__main__":
    main()

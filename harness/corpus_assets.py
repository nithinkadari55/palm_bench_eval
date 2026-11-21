import base64
import io
import os
import shutil

from PIL import Image


def solid(color, size=(100, 100), mode="RGB"):
    return Image.new(mode, size, color)


def build_assets(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    made = {}
    solid((255, 0, 0)).save(os.path.join(out_dir, "red.png"))
    solid((0, 0, 255)).save(os.path.join(out_dir, "blue.jpg"), quality=95)
    solid((0, 255, 0)).convert("P").save(os.path.join(out_dir, "green.gif"))
    solid((255, 255, 0)).save(os.path.join(out_dir, "yellow.webp"), quality=95)
    try:
        solid((255, 128, 0)).save(os.path.join(out_dir, "orange.avif"), quality=95)
        made["avif"] = True
    except Exception as e:  # noqa: BLE001
        made["avif"] = f"unavailable: {e}"
    solid((0, 255, 255, 0), mode="CMYK").save(os.path.join(out_dir, "cmyk-red.jpg"), quality=95)
    exif_src = Image.new("RGB", (200, 100), (255, 0, 0))
    exif_src.paste((0, 0, 255), (100, 0, 200, 100))
    ex = Image.Exif()
    ex[0x0112] = 6
    exif_src.save(os.path.join(out_dir, "exif6.jpg"), quality=95, exif=ex.tobytes())
    wide = Image.new("RGB", (300, 150), (255, 0, 0))
    wide.save(os.path.join(out_dir, "wide-red.png"))
    stripe = Image.new("RGB", (20, 20), (0, 0, 255))
    stripe.save(os.path.join(out_dir, "tile-blue.png"))
    with open(os.path.join(out_dir, "magenta.svg"), "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
                '<rect width="100" height="100" fill="#ff00ff"/></svg>')
    buf = io.BytesIO()
    solid((0, 160, 0)).save(buf, format="PNG")
    made["green_data_uri"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    made["fonts"] = build_fonts(out_dir)
    return made


def _rename_font(src, dst, family, flavor=None):
    from fontTools.ttLib import TTFont
    f = TTFont(src)
    ps = family.replace(" ", "") + "-Regular"
    for rec in f["name"].names:
        if rec.nameID in (1, 16):
            rec.string = family
        elif rec.nameID == 4:
            rec.string = family + " Regular"
        elif rec.nameID == 6:
            rec.string = ps
        elif rec.nameID == 3:
            rec.string = ps + ";bench"
    if flavor:
        f.flavor = flavor
    f.save(dst)


def build_fonts(out_dir):
    res = {}
    serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    if not os.path.exists(serif):
        serif = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        _rename_font(serif, os.path.join(out_dir, "benchface.woff2"), "BenchFace", flavor="woff2")
        res["woff2"] = True
    except Exception as e:  # noqa: BLE001
        res["woff2"] = f"failed: {e}"
    try:
        _rename_font(serif, os.path.join(out_dir, "benchwoff.woff"), "BenchWoff", flavor="woff")
        res["woff"] = True
    except Exception as e:  # noqa: BLE001
        res["woff"] = f"failed: {e}"
    try:
        _rename_font(mono, os.path.join(out_dir, "benchmono.ttf"), "BenchMono")
        res["ttf"] = True
    except Exception as e:  # noqa: BLE001
        res["ttf"] = f"failed: {e}"
    return res


if __name__ == "__main__":
    import sys
    print(build_assets(sys.argv[1]))
    shutil.os.sync() if hasattr(shutil.os, "sync") else None

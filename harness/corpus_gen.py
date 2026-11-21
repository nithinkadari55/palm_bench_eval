import os
import random
import re

from pdfcheck import close, norm

PAGE_W, PAGE_H, MARGIN = 800, 1000, 50
CL, CR, CT, CB = 50, 750, 50, 950

BASE_CSS = """
@page { size: 800px 1000px; margin: 50px; }
html, body { margin: 0; padding: 0; }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 16px; line-height: 20px; color: #000; }
"""

RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
YELLOW, MAGENTA, CYAN = (255, 255, 0), (255, 0, 255), (0, 255, 255)
WHITE, BLACK = (255, 255, 255), (0, 0, 0)

LOREM = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore "
         "magna aliqua enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo "
         "consequat duis aute irure in reprehenderit voluptate velit esse cillum fugiat nulla pariatur").split()


def lorem(n, seed=0):
    r = random.Random(seed)
    return " ".join(r.choice(LOREM) for _ in range(n))


def page(body, css="", head=""):
    return f"<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">{head}<style>{BASE_CSS}{css}</style></head>\n<body>{body}</body></html>\n"


# ---------------------------------------------------------------- check helpers

def C(cat, name, fn):
    return {"cat": cat, "name": name, "fn": fn}


def first(d, tok):
    h = d.find(tok)
    return h[0] if h else None


def present_once(tokens):
    def f(d):
        missing, dup = [], []
        for t in tokens:
            n = len(d.find(t))
            if n == 0:
                missing.append(t)
            elif n > 1:
                dup.append(t)
        return (not missing and not dup), {"missing": missing[:10], "n_missing": len(missing), "dup": dup[:10]}
    return f


def present(tokens):
    def f(d):
        missing = [t for t in tokens if not d.find(t)]
        return not missing, {"missing": missing[:10], "n_missing": len(missing)}
    return f


def absent(tokens):
    def f(d):
        found = [t for t in tokens if d.find(t)]
        return not found, {"found": found}
    return f


def in_order(tokens):
    def f(d):
        prev, bad = None, []
        for t in tokens:
            h = first(d, t)
            if h is None:
                return False, {"missing": t}
            key = (h["page"], round(h["y0"] / 4), h["x0"])
            if prev is not None and key < prev[1]:
                bad.append((prev[0], t))
            prev = (t, key)
        return not bad, {"violations": bad[:5], "n": len(bad)}
    return f


def page_count(lo, hi):
    return lambda d: (lo <= d.n <= hi, {"pages": d.n})


def on_page(tok, p):
    def f(d):
        h = first(d, tok)
        return (h is not None and h["page"] == p), {"page": h and h["page"]}
    return f


def same_page_pairs(pairs):
    def f(d):
        bad = []
        for a, b in pairs:
            ha, hb = first(d, a), first(d, b)
            if not ha or not hb or ha["page"] != hb["page"]:
                bad.append((a, b, ha and ha["page"], hb and hb["page"]))
        return not bad, {"bad": bad[:5], "n_bad": len(bad)}
    return f


def px(p, x, y, rgb, tol=45):
    def f(d):
        if p >= len(d.raster()):
            return False, {"error": "no page"}
        v = d.pixel(p, x, y)
        return close(v, rgb, tol), {"at": (p, x, y), "got": v, "want": rgb}
    return f


def not_px(p, x, y, rgb, tol=45):
    def f(d):
        if p >= len(d.raster()):
            return False, {"error": "no page"}
        v = d.pixel(p, x, y)
        return (v is not None and not close(v, rgb, tol)), {"at": (p, x, y), "got": v, "not": rgb}
    return f


def x_near(tok, x, tol=4):
    def f(d):
        h = first(d, tok)
        return (h is not None and abs(h["x0"] - x) <= tol), {"x0": h and round(h["x0"], 1), "want": x}
    return f


def within_content(tokens, tol=3):
    def f(d):
        bad = []
        for t in tokens:
            for h in d.find(t):
                if h["x0"] < CL - tol or h["x1"] > CR + tol or h["y0"] < CT - tol or h["y1"] > CB + tol:
                    bad.append((t, h["page"], round(h["x0"]), round(h["y0"])))
        return not bad, {"bad": bad[:5], "n_bad": len(bad)}
    return f


def every_page_has(tok, region=None):
    def f(d):
        missing = []
        for pi in range(d.n):
            hs = [h for h in d.find(tok) if h["page"] == pi]
            if region:
                hs = [h for h in hs if region(h)]
            if not hs:
                missing.append(pi + 1)
        return (d.n > 0 and not missing), {"pages_missing": missing[:10], "pages": d.n}
    return f


def text_contains(sub, normalize=True):
    def f(d):
        t = d.all_text()
        ok = (norm(sub) in norm(t)) if normalize else (sub in t)
        return ok, {"want": sub}
    return f


# ---------------------------------------------------------------- documents

def doc_basic_flow():
    toks = [f"PARA{i:03d}" for i in range(1, 41)]
    body = "".join(f"<p>{t} {lorem(90, i)}</p>" for i, t in enumerate(toks))
    return page(body, "p{margin:0 0 12px}"), [
        C("pagination", "all paragraphs present exactly once", present_once(toks)),
        C("pagination", "reading order preserved across pages", in_order(toks)),
        C("pagination", "multi-page output (>=3 pages)", page_count(3, 12)),
        C("pagination", "all text inside page content box", within_content(toks)),
    ], {}


def doc_forced_breaks():
    toks = [f"SECT{i}" for i in range(1, 6)]
    body = "".join(f"<section><h2>{t}</h2><p>{lorem(60, i)}</p></section>" for i, t in enumerate(toks))
    css = "section{break-before:page} h2{margin:0}"

    def first_on_page(d):
        bad = []
        for i, t in enumerate(toks):
            h = first(d, t)
            if not h or h["page"] != i:
                bad.append((t, h and h["page"]))
                continue
            top = min(l.y0 for l in d.pages[i]["lines"])
            if h["y0"] > top + 2:
                bad.append((t, "not top"))
        return not bad, {"bad": bad}
    return page(body, css), [
        C("pagination", "break-before:page puts each section on its own page", first_on_page),
        C("pagination", "exactly 5 pages", page_count(5, 5)),
    ], {}


def doc_break_inside_avoid():
    body = "".join(f"<div class=b><b>BOX{i:02d}S</b><p>{lorem(40, i)}</p><b>BOX{i:02d}E</b></div>" for i in range(12))
    css = ".b{break-inside:avoid;height:300px;border:1px solid #888;margin-bottom:10px;box-sizing:border-box} p{margin:0}"
    pairs = [(f"BOX{i:02d}S", f"BOX{i:02d}E") for i in range(12)]
    return page(body, css), [
        C("pagination", "break-inside:avoid keeps each box on one page", same_page_pairs(pairs)),
        C("pagination", "boxes in order", in_order([p for pr in pairs for p in pr])),
    ], {}


def doc_orphans_widows():
    words = [f"ow{i:03d}" for i in range(400)]
    body = ("<div style='height:820px'></div>" + "<p class=ow>" + " ".join(words[:200]) + "</p>"
            + "<div style='height:300px'></div>" + "<p class=ow>" + " ".join(words[200:]) + "</p>")
    css = "p.ow{orphans:4;widows:4;margin:0;line-height:20px}"

    def check(d):
        res = []
        for seg in (words[:200], words[200:]):
            lines_by_page = {}
            for w in seg:
                h = first(d, w)
                if h:
                    lines_by_page.setdefault(h["page"], set()).add(round(h["y0"] / 5))
            counts = [len(v) for k, v in sorted(lines_by_page.items())]
            res.append(counts)
        ok = all(all(c >= 4 for c in counts) and len(counts) >= 2 for counts in res)
        return ok, {"lines_per_page": res}
    return page(body, css), [
        C("pagination", "orphans:4 / widows:4 honored on split paragraphs", check),
        C("pagination", "all words present", present_once(words)),
    ], {}


def doc_table_thead():
    rows = 150
    trs = "".join(f"<tr><td>R{i:03d}A</td><td>R{i:03d}B {lorem(3, i)}</td><td>R{i:03d}C</td><td>R{i:03d}D</td></tr>" for i in range(rows))
    body = ("<table><thead><tr><th>HDRA</th><th>HDRB</th><th>HDRC</th><th>HDRD</th></tr></thead>"
            f"<tbody>{trs}</tbody><tfoot><tr><td colspan=4>FTRTOK</td></tr></tfoot></table>")
    css = "table{width:700px;border-collapse:collapse} td,th{border:1px solid #999;padding:3px;text-align:left}"
    cells = [f"R{i:03d}{c}" for i in range(rows) for c in "ABCD"]

    def header_each_page(d):
        bad = []
        for pi in range(d.n):
            rs = [h for t in ("R", ) for h in []]
            row_hits = [h for i in range(rows) for h in d.find(f"R{i:03d}A") if h["page"] == pi]
            if not row_hits:
                continue
            hd = [h for h in d.find("HDRA") if h["page"] == pi]
            if not hd or hd[0]["y1"] > min(h["y0"] for h in row_hits) + 1:
                bad.append(pi + 1)
        return not bad, {"pages_without_header": bad}

    def rows_not_split(d):
        bad = []
        for i in range(rows):
            ha, hd = first(d, f"R{i:03d}A"), first(d, f"R{i:03d}D")
            if not ha or not hd or ha["page"] != hd["page"] or abs(ha["y0"] - hd["y0"]) > 3:
                bad.append(i)
        return not bad, {"split_rows": bad[:10], "n": len(bad)}
    return page(body, css), [
        C("pagination", "every cell present exactly once", present_once(cells)),
        C("pagination", "rows in order", in_order([f"R{i:03d}A" for i in range(rows)])),
        C("pagination", "thead repeated at top of every page", header_each_page),
        C("pagination", "rows never split across pages", rows_not_split),
        C("pagination", "tfoot repeated on every page", every_page_has("FTRTOK")),
        C("pagination", "table spans multiple pages", page_count(3, 10)),
    ], {}


def doc_table_structure():
    body = """
<div style="height:100px"><table style="border-collapse:collapse;width:600px;table-layout:fixed">
<colgroup><col style="width:100px"><col style="width:200px"><col style="width:300px"></colgroup>
<tr><td>TA1</td><td>TB1</td><td>TC1</td></tr>
<tr><td rowspan=2>TSPAN</td><td colspan=2>TWIDE</td></tr>
<tr><td>TB3</td><td>TC3</td></tr></table></div>
<div style="height:150px"><table><tr><td>AUTO1 short</td><td>AUTO2 a much longer cell content here</td></tr></table></div>
<table class=bc><tr><td></td><td></td></tr><tr><td></td><td></td></tr></table>
"""
    css = "td{padding:0;border:0;vertical-align:middle} table.bc{border-collapse:collapse} table.bc td{border:4px solid #f00;width:100px;height:50px;padding:0}"

    def rowspan_mid(d):
        s, w, b = first(d, "TSPAN"), first(d, "TWIDE"), first(d, "TB3")
        if not (s and w and b):
            return False, {}
        cy = (s["y0"] + s["y1"]) / 2
        return w["y0"] < cy < b["y1"], {"span_cy": cy, "wide_y": w["y0"], "b3_y": b["y1"]}

    def collapsed_borders(d):
        img = d.raster()[0]
        y = 300 + 25
        row = img[y, 40:400]
        runs, cur = [], 0
        for p in row:
            red = p[0] > 180 and p[1] < 90 and p[2] < 90
            if red:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
        ok = len(runs) == 3 and max(runs) <= 6
        return ok, {"red_runs": runs}
    return page(body, css), [
        C("layout", "fixed table column 1 at x=50", x_near("TA1", 50)),
        C("layout", "fixed table column 2 at x=150", x_near("TB1", 150)),
        C("layout", "fixed table column 3 at x=350", x_near("TC1", 350)),
        C("layout", "colspan cell starts at column 2", x_near("TWIDE", 150)),
        C("layout", "cell under colspan aligned", x_near("TC3", 350)),
        C("layout", "rowspan cell vertically centered across rows", rowspan_mid),
        C("layout", "auto table content present", present(["AUTO1", "AUTO2"])),
        C("graphics", "border-collapse merges adjacent borders", collapsed_borders),
    ], {}


def doc_margin_boxes():
    body = "".join(f"<p>MB{i:02d} {lorem(120, i)}</p>" for i in range(14))
    css = """@page { @top-center { content: "TOPHDR"; font-size: 12px }
             @bottom-right { content: "PG " counter(page) " OF " counter(pages); font-size: 12px } }"""

    def numbers(d):
        bad = []
        for pi in range(d.n):
            want = f"PG {pi + 1} OF {d.n}"
            t = d.page_text(pi)
            if norm(want) not in norm(t):
                bad.append(pi + 1)
        return d.n > 1 and not bad, {"pages_wrong": bad, "pages": d.n}
    return page(body, css), [
        C("pagination", "@top-center margin box on every page", every_page_has("TOPHDR", lambda h: h["y1"] <= 52)),
        C("pagination", "counter(page)/counter(pages) correct in @bottom-right", numbers),
        C("pagination", "body text present", present_once([f"MB{i:02d}" for i in range(14)])),
    ], {}


def doc_named_pages():
    css = """@page { size: A4; margin: 20mm } @page :first { margin-top: 300px }
             @page wide { size: A4 landscape } .wide { page: wide }"""
    body = (f"<p>FIRSTTOK {lorem(50, 1)}</p><div class=wide><p>WIDETOK {lorem(50, 2)}</p></div>"
            f"<p>BACKTOK {lorem(50, 3)}</p>")

    def sizes(d):
        f, w, b = first(d, "FIRSTTOK"), first(d, "WIDETOK"), first(d, "BACKTOK")
        if not (f and w and b):
            return False, {"missing": True}
        s1, s2, s3 = d.page_size_pt(f["page"]), d.page_size_pt(w["page"]), d.page_size_pt(b["page"])
        ok = (abs(s1[0] - 595.3) < 2 and abs(s1[1] - 841.9) < 2 and abs(s2[0] - 841.9) < 2 and abs(s2[1] - 595.3) < 2
              and abs(s3[0] - 595.3) < 2)
        return ok, {"first": s1, "wide": s2, "back": s3}

    def first_margin(d):
        f = first(d, "FIRSTTOK")
        return (f is not None and f["page"] == 0 and f["y0"] >= 296), {"y0": f and f["y0"]}
    return page(body, css), [
        C("pagination", "A4 + named landscape page sizes", sizes),
        C("pagination", "@page :first margin-top applied", first_margin),
    ], {}


def doc_page_size_inches():
    css = "@page { size: 5in 7in; margin: 0.5in }"
    return page(f"<p>SIZETOK {lorem(30)}</p>", css), [
        C("pagination", "@page size: 5in 7in -> 360x504pt", lambda d: (abs(d.page_size_pt(0)[0] - 360) < 1.5 and abs(d.page_size_pt(0)[1] - 504) < 1.5, {"size": d.page_size_pt(0)})),
    ], {}


def doc_page_size_letter_landscape():
    css = "@page { size: letter landscape; margin: 1in }"
    return page(f"<p>LETTERTOK {lorem(30)}</p>", css), [
        C("pagination", "@page size: letter landscape -> 792x612pt", lambda d: (abs(d.page_size_pt(0)[0] - 792) < 1.5 and abs(d.page_size_pt(0)[1] - 612) < 1.5, {"size": d.page_size_pt(0)})),
    ], {}


def doc_flex():
    body = """
<div style="display:flex;justify-content:space-between;width:700px;height:100px">
 <div style="width:150px;height:100px;background:#f00"></div><div style="width:150px;height:100px;background:#0f0"></div><div style="width:150px;height:100px;background:#00f"></div></div>
<div style="display:flex;flex-wrap:wrap;gap:10px;width:700px;height:180px;align-content:flex-start">
 <div class=w style="background:#f00"></div><div class=w style="background:#0f0"></div><div class=w style="background:#00f"></div>
 <div class=w style="background:#ff0"></div><div class=w style="background:#f0f"></div><div class=w style="background:#0ff"></div>
 <div class=w style="background:#000"></div></div>
<div style="display:flex;align-items:center;height:150px;width:700px">
 <div style="width:100px;height:50px;background:#f0f"></div><div style="width:100px;height:150px;background:#0ff"></div></div>
<div style="display:flex;width:700px;height:50px">
 <div style="flex:1;background:#f00"></div><div style="flex:2;background:#00f"></div><div style="width:100px;flex:none;background:#0f0"></div></div>
<div style="display:flex;flex-direction:row-reverse;width:700px;height:50px">
 <div style="width:100px;background:#f00"></div><div style="width:100px;background:#00f"></div></div>
"""
    css = ".w{width:220px;height:50px}"
    return page(body, css), [
        C("layout", "space-between item 1", px(0, 125, 100, RED)),
        C("layout", "space-between item 2 centered", px(0, 400, 100, GREEN)),
        C("layout", "space-between item 3 right", px(0, 675, 100, BLUE)),
        C("layout", "space-between gap empty", px(0, 262, 100, WHITE)),
        C("layout", "flex-wrap row 2 col 1", px(0, 160, 235, YELLOW)),
        C("layout", "flex-wrap row 2 col 3", px(0, 620, 235, CYAN)),
        C("layout", "flex-wrap row 3 col 1", px(0, 160, 295, BLACK)),
        C("layout", "align-items:center offsets short item", px(0, 100, 405, MAGENTA)),
        C("layout", "align-items:center leaves space above", px(0, 100, 345, WHITE)),
        C("layout", "flex-grow 1 share", px(0, 150, 505, RED)),
        C("layout", "flex-grow 2 share", px(0, 450, 505, BLUE)),
        C("layout", "flex:none fixed item", px(0, 700, 505, GREEN)),
        C("layout", "row-reverse first item at right", px(0, 700, 555, RED)),
        C("layout", "row-reverse second item", px(0, 600, 555, BLUE)),
    ], {"no_text": True}


def doc_grid():
    body = """
<div style="display:grid;grid-template-columns:1fr 2fr 1fr;gap:20px;width:700px;grid-auto-rows:100px;height:220px">
 <div style="background:#f00"></div><div style="background:#0f0"></div><div style="background:#00f"></div>
 <div style="background:#ff0"></div><div style="background:#0ff"></div><div style="background:#f0f"></div></div>
<div style="display:grid;grid-template-areas:'head head' 'side main';grid-template-columns:200px 1fr;grid-template-rows:50px 100px;width:700px;height:150px">
 <div style="grid-area:head;background:#f00"></div><div style="grid-area:side;background:#0f0"></div><div style="grid-area:main;background:#00f"></div></div>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:20px;width:700px;grid-auto-rows:50px;height:120px">
 <div style="background:#000"></div><div style="background:#000"></div><div style="background:#000"></div><div style="background:#f0f"></div><div style="background:#0ff"></div></div>
<div style="display:grid;grid-template-columns:repeat(4,100px);grid-auto-rows:50px;height:100px">
 <div style="grid-column:span 3;background:#f00"></div><div style="background:#0f0"></div><div style="grid-column:2 / 5;background:#00f"></div></div>
<div style="display:grid;grid-template-columns:200px 200px;grid-auto-rows:100px;justify-items:center;align-items:end">
 <div style="width:50px;height:50px;background:#f0f"></div></div>
"""
    return page(body), [
        C("layout", "fr track 1", px(0, 132, 100, RED)),
        C("layout", "fr track 2 (2fr)", px(0, 400, 100, GREEN)),
        C("layout", "fr track 3", px(0, 667, 100, BLUE)),
        C("layout", "column gap empty", px(0, 225, 100, WHITE)),
        C("layout", "row 2 track 1", px(0, 132, 220, YELLOW)),
        C("layout", "row 2 track 3", px(0, 667, 220, MAGENTA)),
        C("layout", "template-areas head spans", px(0, 600, 295, RED)),
        C("layout", "template-areas side", px(0, 150, 370, GREEN)),
        C("layout", "template-areas main", px(0, 500, 370, BLUE)),
        C("layout", "auto-fill minmax: 4 columns", px(0, 670, 445, MAGENTA)),
        C("layout", "auto-fill wraps 5th item", px(0, 130, 515, CYAN)),
        C("layout", "span 3", px(0, 200, 565, RED)),
        C("layout", "item after span", px(0, 400, 565, GREEN)),
        C("layout", "explicit line placement 2/5", px(0, 300, 615, BLUE)),
        C("layout", "cell left of placed item empty", px(0, 100, 615, WHITE)),
        C("layout", "justify-items:center + align-items:end", px(0, 150, 715, MAGENTA)),
        C("layout", "align end leaves space above", px(0, 150, 660, WHITE)),
    ], {"no_text": True}


def doc_flex_fragmentation():
    toks = [f"FIX{i:02d}" for i in range(40)]
    items = "".join(f"<div class=i style='background:{'#eef' if i % 2 else '#efe'}'>{t}</div>" for i, t in enumerate(toks))
    css = ".c{display:flex;flex-direction:column} .i{height:60px;margin-bottom:10px;flex:none}"
    return page(f"<div class=c>{items}</div>", css), [
        C("pagination", "flex column fragments: all items present once", present_once(toks)),
        C("pagination", "flex items in order", in_order(toks)),
        C("pagination", "flex items inside page content area (not clipped/overflowing)", within_content(toks)),
        C("pagination", "flex container spans >=3 pages", page_count(3, 6)),
    ], {}


def doc_grid_fragmentation():
    toks = [f"GRI{i:03d}" for i in range(90)]
    items = "".join(f"<div class=g>{t}</div>" for t in toks)
    css = ".c{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;grid-auto-rows:80px} .g{background:#eee}"

    def rows_aligned(d):
        bad = []
        for r in range(30):
            hs = [first(d, toks[r * 3 + k]) for k in range(3)]
            if any(h is None for h in hs) or len({h["page"] for h in hs}) > 1 or max(h["y0"] for h in hs) - min(h["y0"] for h in hs) > 3:
                bad.append(r)
        return not bad, {"bad_rows": bad[:10]}
    return page(f"<div class=c>{items}</div>", css), [
        C("pagination", "grid fragments: all items present once", present_once(toks)),
        C("pagination", "grid items row-major order", in_order(toks)),
        C("pagination", "grid rows stay aligned across fragmentation", rows_aligned),
        C("pagination", "grid items inside page content area", within_content(toks)),
        C("pagination", "grid spans >=3 pages", page_count(3, 6)),
    ], {}


def doc_multicol():
    toks = [f"MC{i:03d}" for i in range(300)]
    toks2 = [f"MD{i:03d}" for i in range(60)]
    body = (f"<div class=mc>{' '.join(toks)}</div><h2 class=span>MCSPANHEAD</h2><div class=mc>{' '.join(toks2)}</div>")
    css = ".mc{column-count:3;column-gap:20px;width:700px} h2.span{column-span:all;margin:0}"
    bands = [(CL - 3, 272), (288, 512), (528, CR + 3)]

    def band(h):
        for i, (a, b) in enumerate(bands):
            if a <= h["x0"] and h["x1"] <= b:
                return i
        return -1

    def distribution(d):
        used = set()
        bad = 0
        for t in toks:
            h = first(d, t)
            if h is None:
                return False, {"missing": t}
            b = band(h)
            if b < 0:
                bad += 1
            used.add((h["page"], b))
        p0 = {b for p, b in used if p == 0}
        return (bad == 0 and p0 == {0, 1, 2}), {"bands_page1": sorted(p0), "out_of_band": bad}

    def column_order(d):
        prev, viol = None, 0
        for t in toks:
            h = first(d, t)
            key = (h["page"], band(h), round(h["y0"] / 4), h["x0"])
            if prev and key < prev:
                viol += 1
            prev = key
        return viol == 0, {"violations": viol}

    def balanced(d):
        bottoms = {}
        for t in toks:
            h = first(d, t)
            if h["page"] == 0:
                b = band(h)
                bottoms[b] = max(bottoms.get(b, 0), h["y1"])
        if len(bottoms) < 3:
            return False, {"bottoms": bottoms}
        return max(bottoms.values()) - min(bottoms.values()) <= 45, {"bottoms": bottoms}

    def spanner(d):
        h = first(d, "MCSPANHEAD")
        last = max((first(d, t) for t in toks), key=lambda h: (h["page"], h["y1"]))
        nxt = first(d, toks2[0])
        return (h is not None and h["x0"] <= 56 and (h["page"], h["y0"]) >= (last["page"], last["y1"] - 2)
                and nxt is not None and (nxt["page"], nxt["y0"]) >= (h["page"], h["y1"] - 2)), {"head": h}
    return page(body, css), [
        C("layout", "multicol: tokens present once", present_once(toks + toks2)),
        C("layout", "multicol: text flows into 3 column bands", distribution),
        C("layout", "multicol: column-major reading order", column_order),
        C("layout", "multicol: column-fill balance", balanced),
        C("layout", "column-span:all heading spans and separates", spanner),
    ], {}


def doc_floats():
    toks = [f"FL{i:03d}" for i in range(220)]
    body = (f"<div style='float:right;width:200px;height:200px;background:#f00'></div><p>{' '.join(toks)}</p>"
            f"<div style='float:left;width:100px;height:150px;background:#00f'></div><p>{lorem(10)}</p>"
            f"<div style='clear:both'>CLEARTOK</div>")
    css = "p{margin:0}"

    def wrap(d):
        near = [first(d, t) for t in toks]
        near = [h for h in near if h and h["page"] == 0]
        beside = [h for h in near if h["y1"] < 245]
        below = [h for h in near if h["y0"] > 260]
        ok = beside and all(h["x1"] <= 553 for h in beside) and any(h["x1"] > 570 for h in below)
        return bool(ok), {"beside_max_x1": max((h["x1"] for h in beside), default=None), "n_beside": len(beside)}

    def clear(d):
        img = d.raster()[0]
        col = img[:, 100]
        blue_rows = [y for y in range(img.shape[0]) if col[y][2] > 180 and col[y][0] < 80 and col[y][1] < 80]
        h = first(d, "CLEARTOK")
        if not blue_rows or not h:
            return False, {"blue": bool(blue_rows), "tok": bool(h)}
        return h["y0"] >= max(blue_rows) - 1, {"float_bottom": max(blue_rows), "clear_y0": h["y0"]}
    return page(body, css), [
        C("layout", "float:right box rendered", px(0, 650, 150, RED)),
        C("layout", "text wraps beside float (line boxes shortened)", wrap),
        C("layout", "clear:both moves below float", clear),
        C("layout", "all wrapped text present", present_once(toks)),
    ], {}


def doc_positioning():
    filler = "".join(f"<p>POS{i:02d} {lorem(100, i)}</p>" for i in range(12))
    body = f"""
<div style="position:relative;width:700px;height:300px">
 <div style="position:absolute;top:100px;left:100px;width:100px;height:50px;background:#f00"></div>
 <div style="position:absolute;right:0;bottom:0;width:100px;height:100px;background:#00f"></div></div>
<div style="position:relative;top:20px;left:30px;width:100px;height:50px;background:#0f0"></div>
<div style="position:fixed;bottom:0;left:0;font-size:12px">FIXEDTOK</div>
<div style="height:40px"></div>{filler}"""
    return page(body), [
        C("layout", "absolute top/left inside relative container", px(0, 200, 175, RED)),
        C("layout", "absolute right/bottom", px(0, 700, 300, BLUE)),
        C("layout", "relative offset", px(0, 130, 395, GREEN)),
        C("layout", "relative offset leaves original spot", px(0, 60, 360, WHITE)),
        C("pagination", "position:fixed repeats on every page", every_page_has("FIXEDTOK")),
    ], {"allow_overlap": True}


def doc_rtl():
    ar = "مرحبا بالعالم هذا اختبار للنص العربي في المستند"
    he = "שלום עולם זהו מבחן לטקסט בעברית"
    body = f"<p dir=rtl lang=ar class=r>{ar}</p><p dir=rtl lang=he class=r>{he}</p><p>LTRTOK left aligned</p>"
    css = "p.r{font-family:'Noto Sans Arabic','Noto Sans Hebrew','DejaVu Sans',sans-serif}"

    def contains_words(words):
        def f(d):
            t = norm(d.all_text())
            miss = [w for w in words if norm(w) not in t and norm(w[::-1]) not in t]
            return len(miss) <= len(words) // 4, {"missing": miss}
        return f

    def right_aligned(d):
        chars = [c for c in d.pages[0]["chars"] if "֐" <= c.t[0] <= "ۿ" or "יִ" <= c.t[0] <= "ﻼ"]
        if not chars:
            return False, {"rtl_chars": 0}
        return max(c.x1 for c in chars) >= CR - 6, {"max_x1": max(c.x1 for c in chars)}
    return page(body, css), [
        C("text", "Arabic text extractable", contains_words(ar.split())),
        C("text", "Hebrew text extractable", contains_words(he.split())),
        C("text", "RTL paragraphs align to the right edge", right_aligned),
        C("text", "LTR paragraph at left", x_near("LTRTOK", CL)),
    ], {}


def doc_cjk():
    zh = ("中文排版测试汉字显示是否正确" * 22)[:300]
    ja = "日本語の組版テストです。ひらがなとカタカナと漢字を含みます。" * 3
    ko = "한국어 조판 테스트입니다 " * 5
    body = f"<p lang=zh>{zh}</p><p lang=ja>{ja}</p><p lang=ko>{ko}</p>"

    def count_cjk(d):
        t = d.all_text()
        n = sum(1 for ch in t if "一" <= ch <= "鿿")
        want = sum(1 for ch in zh + ja if "一" <= ch <= "鿿")
        return n >= 0.97 * want, {"got": n, "want": want}

    def in_box(d):
        bad = [c for p in d.pages for c in p["chars"] if c.x1 > CR + 3 or c.x0 < CL - 3]
        return not bad, {"outside": len(bad)}
    return page(body), [
        C("text", "CJK ideographs all extractable", count_cjk),
        C("text", "Hangul extractable", text_contains("한국어조판테스트입니다")),
        C("text", "CJK lines wrap inside content box", in_box),
    ], {}


def doc_indic():
    words = ["हिन्दी", "पाठ", "परीक्षण", "தமிழ்", "உரை", "சோதனை", "বাংলা", "লেখা", "পরীক্ষা"]
    body = "<p lang=hi>हिन्दी पाठ परीक्षण</p><p lang=ta>தமிழ் உரை சோதனை</p><p lang=bn>বাংলা লেখা পরীক্ষা</p>"

    def f(d):
        t = norm(d.all_text())
        miss = [w for w in words if norm(w) not in t]
        return not miss, {"missing": miss}
    return page(body), [C("text", "Devanagari/Tamil/Bengali shaped and extractable", f)], {}


def doc_emoji():
    body = "<p style='font-size:24px;line-height:30px'>EMJ 😀 👍🏽 👨‍👩‍👧 🇺🇳 ❤️</p>"

    def colorful(d):
        img = d.raster()[0]
        reg = img[45:90, 100:450]
        sat = (reg.max(axis=2) - reg.min(axis=2)) > 60
        return int(sat.sum()) >= 60, {"saturated_px": int(sat.sum())}
    return page(body), [
        C("text", "color emoji rendered in color", colorful),
        C("text", "emoji codepoint extractable", text_contains("😀")),
    ], {}


def doc_webfonts():
    css = """@font-face { font-family: BenchFace; src: url(assets/benchface.woff2) format('woff2'); }
@font-face { font-family: BenchWoff; src: url(assets/benchwoff.woff) format('woff'); }
@font-face { font-family: BenchMono; src: url(assets/benchmono.ttf) format('truetype'); }
.a{font-family:BenchFace} .b{font-family:BenchMono} .c{font-family:BenchWoff}"""
    body = "<p class=a>WEBFONTTOK woff2 face</p><p class=b>TTFTOK truetype face</p><p class=c>WOFFTOK woff1 face</p>"

    def used(fam, tok):
        def f(d):
            h = d.find(tok)
            names = {c.font for p in d.pages for c in p["chars"] if c.t in tok}
            ok = any(fam.lower() in (n or "").lower() for n in names) or any(fam.lower() in k.lower() for k in d.fonts())
            return ok, {"char_fonts": sorted(names)[:5], "pdf_fonts": sorted(d.fonts())[:8], "found": bool(h)}
        return f
    return page(css=css, body=body), [
        C("fonts", "@font-face WOFF2 loaded and embedded", used("BenchFace", "WEBFONTTOK")),
        C("fonts", "@font-face TTF loaded and embedded", used("BenchMono", "TTFTOK")),
        C("fonts", "@font-face WOFF1 loaded and embedded", used("BenchWoff", "WOFFTOK")),
    ], {}


def doc_images(data_uri):
    cells = [
        ("<img src='assets/red.png' class=im>", RED, "PNG"),
        ("<img src='assets/blue.jpg' class=im>", BLUE, "JPEG"),
        ("<img src='assets/green.gif' class=im>", GREEN, "GIF"),
        ("<img src='assets/yellow.webp' class=im>", YELLOW, "WebP"),
        ("<img src='assets/magenta.svg' class=im>", MAGENTA, "SVG via img"),
        ("<svg width=150 height=150><circle cx=75 cy=75 r=70 fill='#00ffff'/></svg>", CYAN, "inline SVG"),
        ("<img src='assets/orange.avif' class=im>", (255, 128, 0), "AVIF"),
        ("<img src='assets/cmyk-red.jpg' class=im>", RED, "CMYK JPEG"),
        (f"<img src='{data_uri}' class=im>", (0, 160, 0), "data: URI PNG"),
        ("<div class=im style=\"background-image:url('assets/tile-blue.png')\"></div>", BLUE, "CSS background-image"),
        ("<img src='assets/wide-red.png' class=im style='object-fit:contain'>", RED, "object-fit:contain center"),
        ("<img src='assets/missing.png' class=im alt='ALTTXT'>", None, "missing image does not crash"),
    ]
    html, checks = [], []
    for i, (el, color, label) in enumerate(cells):
        col, row = i % 4, i // 4
        x, y = col * 170, row * 170
        html.append(f"<div style='position:absolute;left:{x}px;top:{y}px;width:150px;height:150px'>{el}</div>")
        if color:
            checks.append(C("images", label, px(0, CL + x + 75, CT + y + 75, color, 60)))
    checks.append(C("images", "object-fit:contain letterboxes (top white)", px(0, CL + 2 * 170 + 75, CT + 2 * 170 + 15, WHITE, 40)))
    exif = "<div style='position:absolute;left:0;top:520px;width:100px;height:200px'><img src='assets/exif6.jpg' style='width:100px;height:200px;display:block'></div>"
    checks.append(C("images", "EXIF orientation 6 applied (top red)", px(0, CL + 50, CT + 560, RED, 60)))
    checks.append(C("images", "EXIF orientation 6 applied (bottom blue)", px(0, CL + 50, CT + 680, BLUE, 60)))
    body = "<div style='position:relative;width:700px;height:760px'>" + "".join(html) + exif + "</div>"
    return page(body, ".im{width:150px;height:150px;display:block}"), checks, {"no_text": True}


def doc_decorations():
    body = """
<div class=r><div style="box-sizing:border-box;width:200px;height:100px;background:#f00;border:10px solid #00f"></div></div>
<div class=r><div style="width:200px;height:100px;background:#0f0;border-radius:50px"></div></div>
<div class=r><div style="width:200px;height:100px;background:#f00;box-shadow:20px 20px 0 #000"></div></div>
<div class=r><div style="width:600px;height:100px;background:linear-gradient(to right,#f00,#00f)"></div></div>
<div class=r style="display:flex"><div style="width:200px;height:100px;background:#f00;opacity:.5"></div><div style="width:50px"></div><div style="width:200px;height:100px;background:rgba(0,0,255,.5)"></div></div>
<div class=r style="padding-left:0"><div style="width:200px;height:100px;background:radial-gradient(circle,#ff0 0%,#ff0 30%,#f00 100%);outline:5px solid #0f0"></div></div>
<div class=r><p style="font-size:40px;line-height:50px;margin:0;text-shadow:4px 4px 0 #f00">SHADOWTXT</p></div>
"""
    css = ".r{height:120px}"

    def red_near_text(d):
        img = d.raster()[0]
        reg = img[770:840, 50:400]
        red = (reg[:, :, 0] > 180) & (reg[:, :, 1] < 90) & (reg[:, :, 2] < 90)
        return int(red.sum()) > 40, {"red_px": int(red.sum())}
    return page(body, css), [
        C("graphics", "border drawn", px(0, 55, 100, BLUE)),
        C("graphics", "background inside border", px(0, 150, 100, RED)),
        C("graphics", "border-radius clips corner", px(0, 53, 173, WHITE, 30)),
        C("graphics", "border-radius box filled", px(0, 150, 220, GREEN)),
        C("graphics", "box-shadow offset painted", px(0, 260, 400, BLACK)),
        C("graphics", "box-shadow box", px(0, 150, 340, RED)),
        C("graphics", "linear-gradient start", px(0, 58, 460, RED, 60)),
        C("graphics", "linear-gradient end", px(0, 742, 460, BLUE, 60)),
        C("graphics", "linear-gradient midpoint", px(0, 350, 460, (128, 0, 128), 60)),
        C("graphics", "opacity:.5", px(0, 150, 580, (255, 128, 128), 30)),
        C("graphics", "rgba background", px(0, 400, 580, (128, 128, 255), 30)),
        C("graphics", "radial-gradient center", px(0, 150, 700, YELLOW, 50)),
        C("graphics", "radial-gradient edge", px(0, 52, 652, RED, 70)),
        C("graphics", "outline drawn outside box", px(0, 47, 700, GREEN, 50)),
        C("graphics", "text-shadow painted", red_near_text),
    ], {}


def doc_transforms():
    body = """
<div style="height:200px"><div style="margin:50px;width:100px;height:100px;background:#00f;transform:rotate(45deg)"></div></div>
<div style="height:200px"><div style="margin:50px;width:100px;height:100px;background:#0f0;transform:scale(2)"></div></div>
<div style="height:200px"><div style="width:100px;height:100px;background:#f00;transform:translate(200px,50px)"></div></div>
<div style="height:200px;perspective:400px"><div style="margin-left:100px;width:200px;height:150px;background:#f0f;transform:rotateY(60deg)"></div></div>
"""
    return page(body), [
        C("graphics", "rotate(45deg) center", px(0, 150, 150, BLUE)),
        C("graphics", "rotate(45deg) corner rotated away", px(0, 104, 104, WHITE, 40)),
        C("graphics", "rotate(45deg) tip extends above box", px(0, 150, 84, BLUE, 60)),
        C("graphics", "scale(2) grows box", px(0, 60, 260, GREEN)),
        C("graphics", "translate moves box", px(0, 300, 500, RED)),
        C("graphics", "translate vacates original spot", px(0, 100, 500, WHITE)),
        C("graphics", "3D rotateY narrows box (edge empty)", px(0, 156, 725, WHITE, 40)),
        C("graphics", "3D rotateY center painted", px(0, 250, 725, MAGENTA, 60)),
    ], {"no_text": True}


def doc_links():
    head = "<title>BENCH TITLE META</title><meta name=author content='Bench Author'>"
    body = (f"<h1>Bench Document</h1><p><a href='https://example.com/bench'>EXTLINK</a> and <a href='#sec3'>INTLINK</a></p>"
            f"<h2>Section One</h2><p>{lorem(40, 1)}</p><h2>Section Two</h2><p>{lorem(40, 2)}</p>"
            f"<h2 id=sec3>Section Three</h2><p>SEC3TOK</p><h3>Sub Three A</h3><p>{lorem(20, 3)}</p>")
    css = "h2{break-before:page}"

    def ext(d):
        h = first(d, "EXTLINK")
        ls = [l for l in d.links() if l.get("uri", "").startswith("https://example.com/bench")]
        ok = bool(h and ls and any(l["page"] == h["page"] and l["x0"] - 3 <= h["x0"] and l["x1"] + 3 >= h["x1"] and l["y0"] - 3 <= h["y0"] and l["y1"] + 3 >= h["y1"] for l in ls))
        return ok, {"links": ls[:3], "tok": h}

    def internal(d):
        tgt = first(d, "SEC3TOK")
        ls = [l for l in d.links() if "uri" not in l]
        return bool(tgt and any(l.get("dest_page") == tgt["page"] for l in ls)), {"internal": ls[:3], "target_page": tgt and tgt["page"]}

    def outline(d):
        o = d.outline()
        titles = [x["title"] for x in o]
        want = ["Bench Document", "Section One", "Section Two", "Section Three", "Sub Three A"]
        it = iter(titles)
        ordered = all(any(w == t for t in it) for w in want)
        return ordered, {"outline": o[:8]}

    def outline_nesting(d):
        o = {x["title"]: x for x in d.outline()}
        a, b = o.get("Section Three"), o.get("Sub Three A")
        return bool(a and b and b["depth"] > a["depth"]), {"three": a, "sub": b}

    def outline_pages(d):
        o = {x["title"]: x for x in d.outline()}
        tgt = first(d, "SEC3TOK")
        a = o.get("Section Three")
        return bool(a and tgt and a["page"] == tgt["page"]), {"outline_page": a and a["page"], "actual": tgt and tgt["page"]}
    return page(body, css, head), [
        C("navigation", "external link annotation over link text", ext),
        C("navigation", "internal #anchor link to correct page", internal),
        C("navigation", "bookmarks generated from headings, in order", outline),
        C("navigation", "bookmark nesting follows heading levels", outline_nesting),
        C("navigation", "bookmark targets correct page", outline_pages),
        C("navigation", "PDF Title from <title>", lambda d: (d.metadata()["title"] == "BENCH TITLE META", d.metadata())),
        C("navigation", "PDF Author from <meta name=author>", lambda d: (d.metadata()["author"] == "Bench Author", d.metadata())),
    ], {}


def doc_css_modern():
    feats = [
        ("var()", ":root{--g:#0f0} .b1{background:var(--g)}", ""),
        ("calc()", ".b2{border-left:calc(60px * 2) solid #0f0}", ""),
        ("clamp()", ".b3{border-left:clamp(10px, 500px, 120px) solid #0f0}", ""),
        ("max()", ".b4{border-left:max(20px, 120px) solid #0f0}", ""),
        ("CSS nesting", ".w5{ & .b5{background:#0f0} }", ""),
        (":is()", ":is(.zz,.b6).box{background:#0f0}", ""),
        (":where()", ".b7:where(.c7){background:#0f0}", "c7"),
        (":has()", ".b8:has(> span){background:#0f0}", "<span></span>"),
        (":not()", ".b9:not(.nope){background:#0f0}", ""),
        (":nth-child(2n+1)", ".row > .b10:nth-child(2n+1){background:#0f0}", ""),
        ("attribute ^=", ".box[data-x^='abc']{background:#0f0}", "data"),
        ("@media print", "@media print{.b12{background:#0f0}}", ""),
        ("@supports", "@supports (display:grid){.b13{background:#0f0}}", ""),
        ("oklch()", ".b14{background:oklch(0.8664 0.2948 142.5)}", ""),
        ("color-mix()", ".b15{background:color-mix(in srgb, #0f0 100%, #f00 0%)}", ""),
        ("lab()", ".b16{background:lab(87.82 -79.27 80.99)}", ""),
        ("hsl() space syntax", ".b17{background:hsl(120deg 100% 50%)}", ""),
        ("#rrggbbaa", ".b18{background:#00ff00ff}", ""),
        ("rem units", ".b19{border-left:7.5rem solid #0f0}", ""),
        ("inset shorthand", ".b20{position:absolute} .b20 i{position:absolute;inset:0;background:#0f0}", "<i></i>"),
        ("logical properties", ".b21{border-inline-start:120px solid #0f0}", ""),
        ("aspect-ratio", ".b22{height:auto;aspect-ratio:2/1;background:#0f0}", ""),
        ("@layer order", "@layer base, top; @layer top{.b23{background:#0f0}} @layer base{.b23{background:#f00}}", ""),
        ("currentColor", ".b24{color:#0f0;background:currentColor}", ""),
        ("!important", ".b25{background:#0f0 !important} .box.b25{background:#f00}", ""),
    ]
    css = ".box{position:absolute;box-sizing:border-box;width:120px;height:60px;background:#f00}"
    boxes, checks = [], []
    for i, (label, rule, extra) in enumerate(feats):
        n = i + 1
        col, row = i % 5, i // 5
        x, y = col * 130, row * 70
        css += "\n" + rule
        cls = f"box b{n}" + (" c7" if extra == "c7" else "")
        attrs = " data-x='abcdef'" if extra == "data" else ""
        inner = extra if extra.startswith("<") else ""
        el = f"<div class='{cls}'{attrs} style='left:{x}px;top:{y}px'>{inner}</div>"
        if n == 5:
            el = f"<div class=w5>{el}</div>"
        if n == 10:
            el = f"<div class=row>{el}</div>"
        boxes.append(el)
        checks.append(C("css", label, px(0, CL + x + 60, CT + y + 30, GREEN, 70)))
    css += """
@media print { .screenonly { display:none } } @media screen { .printonly { display:none } }
.tt{text-transform:uppercase} .bf::before{content:"BEFORETOK "} .af::after{content:" AFTERTOK"}"""
    body = ("<div style='position:relative;height:380px'>" + "".join(boxes) + "</div>"
            "<p class=printonly>PRINTONLYTOK</p><p class=screenonly>SCREENONLYTOK</p>"
            "<p class=tt>transformme</p><p class=bf>gen</p><p class=af>gen</p>")
    checks += [
        C("css", "@media print applied to paged output", present(["PRINTONLYTOK"])),
        C("css", "@media screen excluded from paged output", absent(["SCREENONLYTOK"])),
        C("css", "text-transform:uppercase", present(["TRANSFORMME"])),
        C("css", "::before generated content", present(["BEFORETOK"])),
        C("css", "::after generated content", present(["AFTERTOK"])),
    ]
    return page(body, css), checks, {}


def doc_malformed():
    body = ("<p>MAL01 unclosed paragraph<p>MAL02 next<div>MAL03 <b>bold <i>MAL04 misnested</b> italic</i></div>"
            "<table><tr><td>MAL05 cell<td>MAL06 cell</table></div></div></span>"
            "<unknowntag>MAL07 unknown</unknowntag> MAL08 &notanentity; &amp; a < b > c "
            "<p>MAL09 \u0000 null char</p><ul><li>MAL10 item<li>MAL11 item</ul><br/><br><hr>"
            "<p title=\"unterminated>MAL12 after bad attr</p><p>MAL13 end")
    raw = "﻿<!DOCTYPE html><html><head><meta charset=utf-8><style>" + BASE_CSS + "</style><body>" + body
    toks = [f"MAL{i:02d}" for i in range(1, 14) if i != 12]
    return raw, [
        C("robustness", "malformed HTML: all recoverable text present", present(toks)),
    ], {}


def doc_deep_nesting():
    n = 3000
    body = "<div>" * n + "DEEPTOK" + "</div>" * n
    return page(body), [C("robustness", "3000-level nesting renders (no stack overflow)", present(["DEEPTOK"]))], {}


def doc_wide_dom():
    body = "<p>" + " ".join(f"<span>w{i}</span>" for i in range(20000)) + "</p><p>WIDEEND</p>"
    return page(body), [C("robustness", "20k sibling inline elements render", present(["WIDEEND", "w19999"]))], {}


def doc_long_words():
    long1 = "LONGA" + "x" * 400
    long2 = "LONGB" + "y" * 400
    body = (f"<p style='overflow-wrap:anywhere'>{long1}</p><p style='word-break:break-all'>{long2}</p>"
            f"<p style='overflow-wrap:break-word'>https://example.com/{'segment/' * 40}LONGURLEND</p>")

    def inside(d):
        bad = [c for p in d.pages for c in p["chars"] if c.x1 > CR + 3]
        return not bad, {"chars_beyond_right_edge": len(bad)}
    return page(body), [
        C("text", "overflow-wrap/word-break keep long words inside the page", inside),
        C("text", "long URL fully present", present(["LONGURLEND"])),
    ], {}


def doc_stress_100():
    secs = []
    for s in range(50):
        rows = "".join(f"<tr><td>S{s:02d}R{r:02d}</td><td>{lorem(6, s * 100 + r)}</td><td>{(s + 1) * (r + 3) * 7.5:.2f}</td></tr>" for r in range(30))
        bars = "".join(f"<rect x='{20 + i * 55}' y='{200 - ((s * 7 + i * 13) % 150)}' width='40' height='{(s * 7 + i * 13) % 150}' fill='#36c'/>" for i in range(10))
        secs.append(f"<section><h2>SEC{s:03d} Quarterly section {s}</h2><p>{lorem(160, s)}</p><p>{lorem(160, s + 500)}</p>"
                    f"<svg width='600' height='220'>{bars}</svg>"
                    f"<table><thead><tr><th>ID</th><th>Description</th><th>Amount</th></tr></thead><tbody>{rows}</tbody></table></section>")
    css = "section{break-before:page} table{width:700px;border-collapse:collapse} td,th{border:1px solid #ccc;padding:2px 4px}"
    toks = [f"SEC{s:03d}" for s in range(50)]
    return page("".join(secs), css), [
        C("robustness", "~100-page document renders", page_count(80, 140)),
        C("robustness", "all sections present in order", in_order(toks)),
        C("robustness", "all table rows present", present([f"S{s:02d}R{r:02d}" for s in range(0, 50, 7) for r in range(30)])),
    ], {"perf": True}


def doc_lists_counters():
    ol = "".join(f"<li>LI{i:02d}</li>" for i in range(1, 31))
    roman = "".join(f"<li>RO{i:02d}</li>" for i in range(1, 31))
    nest = "<ol class=nest><li>A<ol class=nest><li>B<ol class=nest><li>C</li></ol></li><li>B2<ol class=nest><li>NESTTOK</li></ol></li></ol></li></ol>"
    css = """body{counter-reset:chap} h2{counter-increment:chap;margin:0} h2::before{content:"Chapter " counter(chap) ": "}
ol.roman{list-style-type:upper-roman} ol.nest{counter-reset:item;list-style:none} ol.nest>li::before{counter-increment:item;content:counters(item,".") " "}"""
    body = f"<h2>A</h2><h2>B</h2><h2>C</h2><ol>{ol}</ol><ol class=roman>{roman}</ol>{nest}"
    return page(body, css), [
        C("css", "decimal list markers", text_contains("29.LI29")),
        C("css", "upper-roman list markers", text_contains("XXIX.RO29")),
        C("css", "counter() in ::before", text_contains("Chapter 3:")),
        C("css", "nested counters()", text_contains("1.2.1NESTTOK")),
    ], {}


def doc_invoice():
    items = "".join(f"<tr><td>ITEM{i:02d}</td><td>Consulting services package {i}</td><td class=n>{i + 1}</td><td class=n>${(i + 1) * 123.45:,.2f}</td></tr>" for i in range(25))
    body = f"""
<header class=hd><div><div class=logo>ACME CORP</div><div>123 Market Street<br>San Francisco, CA</div></div>
<div class=meta><h1>INVOICE</h1><div>INV-2026-0042</div><div>Due: 2026-12-31</div></div></header>
<section class=parties><div><h3>Bill to</h3><p>Globex Inc.<br>42 Elm Road</p></div><div><h3>Ship to</h3><p>Globex Warehouse<br>7 Dock St</p></div></section>
<table class=items><thead><tr><th>SKU</th><th>Description</th><th>Qty</th><th>Amount</th></tr></thead><tbody>{items}</tbody></table>
<div class=tot><div>Subtotal <b>$40,123.45</b></div><div>Tax <b>$3,210.00</b></div><div class=grand>TOTALDUE $12,345.67</div></div>
<footer>Thank you for your business. Payment terms net 30.</footer>"""
    css = """.hd{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #222;padding-bottom:12px}
.logo{font-size:28px;font-weight:bold;color:#1a56db} .meta{text-align:right} .meta h1{margin:0;font-size:32px;letter-spacing:2px}
.parties{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:16px 0} h3{margin:0 0 4px;font-size:13px;text-transform:uppercase;color:#666}
.items{width:100%;border-collapse:collapse} .items th{background:#1a56db;color:#fff;text-align:left;padding:6px}
.items td{padding:5px 6px;border-bottom:1px solid #e5e7eb} .n{text-align:right} .items tr:nth-child(even) td{background:#f9fafb}
.tot{margin-left:auto;width:280px;margin-top:16px} .tot div{display:flex;justify-content:space-between;padding:4px 0} .grand{font-size:20px;font-weight:bold;border-top:2px solid #222}
footer{margin-top:24px;font-size:12px;color:#666}"""

    def amounts_aligned(d):
        xs = {}
        for i in range(25):
            h = first(d, f"${(i + 1) * 123.45:,.2f}")
            if h:
                xs.setdefault(h["page"], []).append(h["x1"])
        if not xs:
            return False, {}
        spread = max(max(v) - min(v) for v in xs.values())
        return spread <= 2.5, {"right_edge_spread": spread}
    return page(body, css), [
        C("layout", "invoice: all line items present", present_once([f"ITEM{i:02d}" for i in range(25)])),
        C("layout", "invoice: key fields present", present(["INV-2026-0042", "TOTALDUE", "$12,345.67", "INVOICE"])),
        C("layout", "invoice: right-aligned amounts share right edge", amounts_aligned),
        C("layout", "invoice: header right block at right", lambda d: ((first(d, "INVOICE") or {"x1": 0})["x1"] >= CR - 6, {"x1": (first(d, "INVOICE") or {}).get("x1")})),
    ], {}


def doc_report_svg():
    bars = [(60, 120, "#e11"), (160, 60, "#1e1"), (260, 180, "#11e")]
    rects = "".join(f"<rect x='{x}' y='{250 - h}' width='60' height='{h}' fill='{c}'/>" for x, h, c in bars)
    body = (f"<svg width='700' height='300' style='display:block'><rect x='0' y='0' width='700' height='300' fill='#fff' stroke='#999'/>{rects}"
            f"<text x='400' y='40' font-size='20' font-family='DejaVu Sans'>SVGTEXTTOK</text>"
            f"<line x1='40' y1='250' x2='660' y2='250' stroke='#000' stroke-width='2'/></svg>"
            f"<div class=cards><div class=card>CARD1 Revenue</div><div class=card>CARD2 Users</div><div class=card>CARD3 Churn</div></div>")
    css = ".cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:16px} .card{border:1px solid #ddd;border-radius:8px;padding:16px;box-shadow:0 2px 6px rgba(0,0,0,.15)}"
    return page(body, css), [
        C("graphics", "inline SVG bar 1", px(0, CL + 90, CT + 200, (238, 17, 17), 50)),
        C("graphics", "inline SVG bar 2", px(0, CL + 190, CT + 220, (17, 238, 17), 50)),
        C("graphics", "inline SVG bar 3", px(0, CL + 290, CT + 150, (17, 17, 238), 50)),
        C("graphics", "inline SVG empty area", px(0, CL + 550, CT + 200, WHITE, 20)),
        C("pdf", "SVG <text> kept as selectable text", present(["SVGTEXTTOK"])),
        C("layout", "cards after SVG", present(["CARD1", "CARD2", "CARD3"])),
    ], {}


def doc_hyphenation():
    words = "internationalization characteristically incomprehensibilities uncharacteristically counterrevolutionaries electroencephalography"
    body = (f"<p lang=en class=hy>{words} {words}</p>"
            "<p class=sh>Donaudampf&shy;schifffahrts&shy;gesellschafts&shy;kapitän SOFTTOK</p>")
    css = ".hy{hyphens:auto;-webkit-hyphens:auto;width:150px;margin:0 0 20px} .sh{width:120px}"

    def hyphenated(d):
        ends = [l.text for l in d.pages[0]["lines"] if l.x0 < CL + 160 and l.text.rstrip().endswith(("-", "‐", "­"))]
        return len(ends) >= 2, {"hyphen_line_ends": ends[:5]}

    def no_overflow(d):
        bad = [l.text for l in d.pages[0]["lines"] if l.x0 < CL + 10 and l.x1 > CL + 150 + 3 and "SOFTTOK" not in l.text and "Donau" not in l.text]
        return not bad, {"overflowing_lines": bad[:5]}

    def soft(d):
        ends = [l.text for l in d.pages[0]["lines"] if l.text.rstrip().endswith(("-", "‐", "­")) and any(k in l.text for k in ("Donau", "schiff", "gesell"))]
        return bool(ends), {"ends": ends}
    return page(body, css), [
        C("text", "hyphens:auto inserts hyphens", hyphenated),
        C("text", "hyphens:auto keeps long words inside 150px", no_overflow),
        C("text", "&shy; shows visible hyphen at break", soft),
    ], {}


def doc_justify():
    body = f"<p style='text-align:justify;width:700px'>JUSTTOK {lorem(150, 7)}</p>"

    def check(d):
        ls = [l for l in d.pages[0]["lines"]]
        if len(ls) < 4:
            return False, {"lines": len(ls)}
        body_lines = ls[:-1]
        bad = [round(l.x1, 1) for l in body_lines if abs(l.x1 - CR) > 3 or abs(l.x0 - CL) > 3]
        return not bad, {"bad_right_edges": bad[:5], "lines": len(ls)}
    return page(body), [C("text", "text-align:justify: all but last line flush both edges", check)], {}


def doc_whitespace():
    body = ("<pre style=\"font-family:'DejaVu Sans Mono';font-size:16px;tab-size:4\">PRE0\n    PRE1\n\tPRE2\n</pre>"
            "<p style='white-space:pre-wrap'>PW1    PW2</p><p style='white-space:nowrap'>NOWRAPTOK</p>")

    def indent(d):
        a, b, c = first(d, "PRE0"), first(d, "PRE1"), first(d, "PRE2")
        if not (a and b and c):
            return False, {}
        adv = (a["x1"] - a["x0"]) / 4
        return abs((b["x0"] - a["x0"]) - 4 * adv) <= 2.5 and abs((c["x0"] - a["x0"]) - 4 * adv) <= 2.5, {"adv": adv, "d1": b["x0"] - a["x0"], "d2": c["x0"] - a["x0"]}

    def prewrap(d):
        a, b = first(d, "PW1"), first(d, "PW2")
        return bool(a and b and b["x0"] - a["x1"] > 25), {"gap": a and b and b["x0"] - a["x1"]}
    return page(body), [
        C("text", "white-space:pre keeps spaces; tab-size:4", indent),
        C("text", "white-space:pre-wrap preserves runs of spaces", prewrap),
    ], {}


def doc_overflow_clip():
    body = """
<div style="width:200px;height:50px;overflow:hidden;background:#fff"><div style="width:200px;height:200px;background:#f00"></div></div>
<div style="height:100px"></div>
<div style="position:relative;width:200px;height:50px;overflow:hidden"><div style="position:absolute;top:70px;left:0;font-size:20px">CLIPPEDTOK</div></div>
<div style="width:200px;height:50px;overflow:clip;margin-top:50px"><div style="width:200px;height:200px;background:#00f"></div></div>
"""

    def text_hidden(d):
        img = d.raster()[0]
        reg = img[CT + 150 + 60:CT + 150 + 100, CL:CL + 250]
        dark = (reg.max(axis=2) < 100).sum()
        return int(dark) == 0, {"dark_px_in_clipped_region": int(dark)}
    return page(body), [
        C("graphics", "overflow:hidden content visible inside", px(0, 150, 75, RED)),
        C("graphics", "overflow:hidden clips below box", px(0, 150, 130, WHITE)),
        C("graphics", "overflow:hidden clips text", text_hidden),
        C("graphics", "overflow:clip clips", px(0, 150, 330, WHITE)),
    ], {"allow_hidden_text": True}


def doc_zindex():
    body = """
<div style="position:relative;height:400px">
 <div style="position:absolute;left:0;top:0;width:200px;height:200px;background:#00f;z-index:2"></div>
 <div style="position:absolute;left:100px;top:100px;width:200px;height:200px;background:#f00;z-index:1"></div>
 <div style="position:absolute;left:400px;top:0;width:200px;height:200px;background:#ff0;z-index:0">
   <div style="position:absolute;left:50px;top:50px;width:100px;height:100px;background:#000;z-index:-1"></div></div>
</div>"""
    return page(body), [
        C("graphics", "higher z-index paints on top", px(0, 200, 200, BLUE)),
        C("graphics", "lower z-index visible outside overlap", px(0, 320, 320, RED)),
        C("graphics", "negative z-index child above stacking-context root background", px(0, 550, 150, BLACK)),
    ], {"no_text": True}


def doc_vertical():
    body = "<div style=\"writing-mode:vertical-rl;height:400px;font-size:20px;line-height:30px;font-family:'Noto Sans CJK JP','Noto Sans CJK SC',sans-serif\">縦書きのテスト文章です。二行目の文章もあります。</div>"

    def check(d):
        cs = [c for c in d.pages[0]["chars"] if "぀" <= c.t <= "鿿"]
        if len(cs) < 6:
            return False, {"cjk_chars": len(cs)}
        first5 = cs[:0]
        col = sorted(cs, key=lambda c: (-round(c.x0 / 10), c.y0))
        head = col[:5]
        xs = [c.x0 for c in head]
        ys = [c.y0 for c in head]
        ok = max(xs) - min(xs) <= 4 and all(ys[i] < ys[i + 1] for i in range(4)) and max(c.x1 for c in cs) > CR - 60
        return ok, {"xs": [round(x) for x in xs], "ys": [round(y) for y in ys]}
    return page(body), [C("text", "writing-mode:vertical-rl stacks glyphs top-to-bottom, columns right-to-left", check)], {"allow_overlap": True}


def doc_js():
    body = ("<p id=x>JSPLACEHOLDER</p><script>document.getElementById('x').textContent='JSINSERTED';"
            "var p=document.createElement('p');p.textContent='JSAPPENDED';document.body.appendChild(p);</script>"
            "<script>document.write('<p>JSWRITTEN</p>')</script>")
    return page(body), [
        C("js", "script modifies DOM before layout", present(["JSINSERTED"])),
        C("js", "script appends nodes", present(["JSAPPENDED"])),
        C("js", "document.write during parse", present(["JSWRITTEN"])),
        C("js", "pre-script content replaced", absent(["JSPLACEHOLDER"])),
    ], {}


def doc_box_model():
    body = """
<div style="height:50px;margin-bottom:20px;background:#f00"></div>
<div style="height:50px;margin-top:30px;background:#00f"></div>
<div style="height:30px"></div>
<div style="width:200px;height:50px;padding:20px;border:5px solid #0f0;background:#ff0"></div>
<div style="box-sizing:border-box;width:200px;height:90px;padding:20px;border:5px solid #f0f;background:#0ff"></div>
<div style="width:50%;height:40px;background:#000"></div>
"""
    return page(body), [
        C("layout", "margin collapsing (30px wins, not 50px)", px(0, 100, 135, BLUE)),
        C("layout", "gap after collapsed margin", px(0, 100, 115, WHITE)),
        C("layout", "content-box: border at width+2*padding", px(0, 50 + 242, 210, GREEN)),
        C("layout", "content-box: padding area has background", px(0, 50 + 225, 210, YELLOW)),
        C("layout", "border-box: total width 200", px(0, 50 + 197, 310, MAGENTA)),
        C("layout", "border-box: nothing beyond 200", px(0, 50 + 206, 310, WHITE)),
        C("layout", "percentage width = 50% of 700", px(0, 50 + 345, 380, BLACK)),
        C("layout", "percentage width stops at 350", px(0, 50 + 356, 380, WHITE)),
    ], {"no_text": True}


def doc_footnotes():
    body = (f"<p>{lorem(60, 1)} FNCALLTOK<span class=fn>FNBODY1 footnote text.</span> {lorem(200, 2)}</p>")
    css = ".fn{float:footnote}"

    def check(d):
        c, b = first(d, "FNCALLTOK"), first(d, "FNBODY1")
        if not (c and b):
            return False, {"call": bool(c), "body": bool(b)}
        return b["page"] == c["page"] and b["y0"] > 650, {"call": c, "body": b}
    return page(body, css), [C("pagination", "float:footnote placed at page bottom", check)], {}


def doc_running_strings():
    css = """h1{string-set:chap content();break-before:page;margin:0} @page{@top-left{content:string(chap);font-size:12px}}"""
    body = (f"<h1>CHAPALPHA</h1><p>{lorem(500, 1)}</p><h1>CHAPBETA</h1><p>{lorem(500, 2)}</p>")

    def check(d):
        a, b = first(d, "CHAPBETA"), None
        bad = []
        for pi in range(d.n):
            hs = [h for tok in ("CHAPALPHA", "CHAPBETA") for h in d.find(tok) if h["page"] == pi and h["y1"] <= 52]
            want = "CHAPBETA" if a and pi >= a["page"] else "CHAPALPHA"
            if not any(d.page_text(pi).find(want) >= 0 and h for h in hs):
                bad.append(pi + 1)
        return d.n >= 3 and not bad, {"pages_wrong": bad, "pages": d.n}
    return page(body, css), [C("pagination", "string-set + string() running headers", check)], {}


def doc_running_elements():
    css = ".rf{position:running(footer)} @page{@bottom-center{content:element(footer)}}"
    body = "<div class=rf>RUNFOOT</div>" + "".join(f"<p>{lorem(150, i)}</p>" for i in range(10))
    return page(body, css), [
        C("pagination", "position:running() element in every page margin", every_page_has("RUNFOOT", lambda h: h["y0"] >= 948)),
    ], {}


def doc_target_counter():
    css = "a.toc::after{content:' p' target-counter(attr(href url), page)} h2{break-before:page}"
    body = ("<p><a class=toc href='#c1'>TOCONE</a></p><p><a class=toc href='#c3'>TOCTHREE</a></p>"
            + "".join(f"<h2 id=c{i}>CHAPHEAD{i}</h2><p>{lorem(50, i)}</p>" for i in range(1, 4)))

    def check(d):
        tgt = first(d, "CHAPHEAD3")
        if not tgt:
            return False, {}
        want = f"TOCTHREE p{tgt['page'] + 1}"
        return norm(want) in norm(d.all_text()), {"want": want}
    return page(body, css), [C("navigation", "target-counter() TOC page numbers", check)], {}


def doc_break_after_avoid():
    body = (f"<div style='height:860px'></div><h2 style='break-after:avoid;margin:0'>KEEPHEAD</h2>"
            f"<p style='margin:0'>KEEPBODY {lorem(80)}</p>")
    return page(body), [C("pagination", "break-after:avoid keeps heading with next block", same_page_pairs([("KEEPHEAD", "KEEPBODY")]))], {}


def all_docs(assets):
    uri = assets.get("green_data_uri", "")
    return {
        "p01_basic_flow": doc_basic_flow,
        "p02_forced_breaks": doc_forced_breaks,
        "p03_break_inside_avoid": doc_break_inside_avoid,
        "p04_orphans_widows": doc_orphans_widows,
        "p05_table_thead_repeat": doc_table_thead,
        "p06_margin_boxes": doc_margin_boxes,
        "p07_named_pages": doc_named_pages,
        "p08_page_size_inches": doc_page_size_inches,
        "p09_page_size_letter_landscape": doc_page_size_letter_landscape,
        "p10_flex_fragmentation": doc_flex_fragmentation,
        "p11_grid_fragmentation": doc_grid_fragmentation,
        "p12_footnotes": doc_footnotes,
        "p13_running_strings": doc_running_strings,
        "p14_running_elements": doc_running_elements,
        "p15_break_after_avoid": doc_break_after_avoid,
        "l01_table_structure": doc_table_structure,
        "l02_flex": doc_flex,
        "l03_grid": doc_grid,
        "l04_multicol": doc_multicol,
        "l05_floats": doc_floats,
        "l06_positioning": doc_positioning,
        "l07_box_model": doc_box_model,
        "l08_invoice": doc_invoice,
        "t01_rtl": doc_rtl,
        "t02_cjk": doc_cjk,
        "t03_indic": doc_indic,
        "t04_emoji": doc_emoji,
        "t05_long_words": doc_long_words,
        "t06_hyphenation": doc_hyphenation,
        "t07_justify": doc_justify,
        "t08_whitespace": doc_whitespace,
        "t09_vertical": doc_vertical,
        "f01_webfonts": doc_webfonts,
        "i01_images": lambda: doc_images(uri),
        "g01_decorations": doc_decorations,
        "g02_transforms": doc_transforms,
        "g03_overflow_clip": doc_overflow_clip,
        "g04_zindex": doc_zindex,
        "g05_report_svg": doc_report_svg,
        "n01_links_bookmarks_meta": doc_links,
        "n02_target_counter": doc_target_counter,
        "c01_css_modern": doc_css_modern,
        "c02_lists_counters": doc_lists_counters,
        "r01_malformed": doc_malformed,
        "r02_deep_nesting": doc_deep_nesting,
        "r03_wide_dom": doc_wide_dom,
        "r04_stress_100_pages": doc_stress_100,
        "j01_javascript": doc_js,
    }

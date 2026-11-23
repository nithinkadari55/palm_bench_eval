from gen_lib import (FONT_STACKS, MONO_STACKS, PALETTES, PRINT_ADJUST, SERIF_STACKS, esc, page_rule, util_css)

SANS_STACKS = [s for s in FONT_STACKS if s not in SERIF_STACKS]
SCRIPT_STACKS = ["'Great Vibes', 'Brush Script MT', cursive", "'Pinyon Script', 'Snell Roundhand', cursive",
                 "'Dancing Script', cursive", "'Playfair Display', Georgia, serif", "'Cormorant Garamond', 'Times New Roman', serif"]


class Style:
    def __init__(self, r, serif=None, base=None):
        self.r = r
        self.p = r.choice(PALETTES)
        if serif is None:
            serif = r.random() < 0.25
        self.font = r.choice(SERIF_STACKS if serif else SANS_STACKS)
        self.head_font = self.font if r.random() < 0.65 else r.choice(FONT_STACKS)
        self.mono = r.choice(MONO_STACKS)
        self.base = base or r.choice(["10pt", "10.5pt", "11pt", "11pt", "12pt", "13px", "14px", "14px", "15px", "16px"])
        self.lh = r.choice(["1.4", "1.45", "1.5", "1.5", "1.6", "1.65"])
        self.vars = r.random() < 0.5
        self.reset = r.choice(["none", "border-box", "border-box", "star-zero"])
        self.util = r.random() < 0.3
        self.radius = r.choice([0, 3, 4, 6, 8, 8, 12, 16])
        self.shadow = r.random() < 0.45
        self.gradient = r.random() < 0.4
        self.table_variant = r.choice(["striped", "bordered", "minimal", "header-dark", "rounded", "lined"])
        self.header_variant = r.choice(["band", "split", "centered", "accent", "gradient-band", "split"])

    def c(self, k):
        return f"var(--{k})" if self.vars else self.p[k]

    def shadow_css(self, strength=1):
        if not self.shadow:
            return ""
        s = ["0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08)",
             "0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06)",
             "0 10px 25px -5px rgba(0,0,0,0.12), 0 8px 10px -6px rgba(0,0,0,0.08)"][min(strength, 2)]
        return f"box-shadow: {s};"

    def bg_strong(self):
        if self.gradient:
            ang = self.r.choice(["135deg", "90deg", "120deg", "to right", "to bottom right", "160deg"])
            return f"background: linear-gradient({ang}, {self.c('primary')}, {self.c('dark') if self.r.random() < 0.5 else self.c('accent')});"
        return f"background: {self.c('primary')};"


def base_css(st, page_css="", extra="", h_scale=1.0):
    r = st.r
    p = st.p
    out = [page_css]
    if st.vars:
        out.append(":root {\n" + "".join(f"  --{k}: {p[k]};\n" for k in ("primary", "accent", "text", "muted", "border", "soft", "dark"))
                   + f"  --radius: {st.radius}px;\n}}\n")
    if st.reset == "border-box":
        out.append("*, *::before, *::after { box-sizing: border-box; }\nhtml, body { margin: 0; padding: 0; }\n")
    elif st.reset == "star-zero":
        out.append("* { margin: 0; padding: 0; box-sizing: border-box; }\np { margin-bottom: 0.75em; }\nul, ol { padding-left: 1.4em; margin-bottom: 0.75em; }\n")
    out.append(f"body {{\n  font-family: {st.font};\n  font-size: {st.base};\n  line-height: {st.lh};\n  color: {st.c('text')};\n"
               + ("  background: #fff;\n" if r.random() < 0.5 else "") + "}\n")
    h1 = round(r.choice([1.8, 2.0, 2.2, 2.4, 2.6]) * h_scale, 2)
    out.append(f"h1, h2, h3, h4 {{ font-family: {st.head_font}; color: {st.c('dark') if r.random() < 0.5 else st.c('text')}; line-height: 1.25; }}\n"
               f"h1 {{ font-size: {h1}em; margin: 0 0 0.4em; }}\nh2 {{ font-size: {round(h1 * 0.62, 2)}em; margin: 1.2em 0 0.5em; }}\n"
               f"h3 {{ font-size: {round(h1 * 0.5, 2)}em; margin: 1em 0 0.4em; }}\n")
    if r.random() < 0.6:
        out.append(PRINT_ADJUST)
    if st.util:
        out.append(util_css(p))
    out.append(extra)
    return "\n".join(x for x in out if x)


def page_css(st, r, title=None, **kw):
    return page_rule(r, header_text=(title or "")[:40].replace('"', "'") or None, font=st.font if r.random() < 0.3 else None, **kw)


def table_css(st, cls="tbl", variant=None, font_size=None):
    v = variant or st.table_variant
    c = st.c
    fs = f"font-size: {font_size};" if font_size else ""
    base = (f".{cls} {{ width: 100%; border-collapse: collapse; {fs} }}\n"
            f".{cls} th, .{cls} td {{ padding: {st.r.choice(['6px 8px', '8px 10px', '10px 12px', '5px 6px', '0.5rem 0.75rem'])}; text-align: left; vertical-align: top; }}\n"
            f".{cls} .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}\n"
            f".{cls} thead {{ display: table-header-group; }}\n.{cls} tfoot {{ display: table-footer-group; }}\n"
            f".{cls} tr {{ break-inside: avoid; page-break-inside: avoid; }}\n")
    if v == "striped":
        base += (f".{cls} thead th {{ background: {c('soft')}; color: {c('dark')}; font-weight: 600; border-bottom: 2px solid {c('primary')}; }}\n"
                 f".{cls} tbody tr:nth-child(even) {{ background: #f9fafb; }}\n.{cls} td {{ border-bottom: 1px solid {c('border')}; }}\n")
    elif v == "bordered":
        base += (f".{cls} th, .{cls} td {{ border: 1px solid {c('border')}; }}\n.{cls} thead th {{ background: #f3f4f6; font-weight: bold; }}\n")
    elif v == "minimal":
        base += (f".{cls} thead th {{ font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.05em; color: {c('muted')}; border-bottom: 1px solid {c('text')}; }}\n"
                 f".{cls} td {{ border-bottom: 1px solid {c('border')}; }}\n")
    elif v == "header-dark":
        base += (f".{cls} thead th {{ background: {c('dark')}; color: #fff; font-weight: 600; }}\n"
                 f".{cls} tbody tr:nth-child(odd) {{ background: {c('soft')}; }}\n")
    elif v == "rounded":
        base = base.replace("border-collapse: collapse;", "border-collapse: separate; border-spacing: 0;")
        base += (f".{cls} {{ border: 1px solid {c('border')}; border-radius: {max(st.radius, 6)}px; overflow: hidden; }}\n"
                 f".{cls} thead th {{ background: {c('primary')}; color: #fff; }}\n.{cls} td {{ border-top: 1px solid {c('border')}; }}\n")
    else:
        base += (f".{cls} thead th {{ border-top: 2px solid {c('text')}; border-bottom: 1px solid {c('text')}; }}\n"
                 f".{cls} tbody tr:last-child td {{ border-bottom: 2px solid {c('text')}; }}\n")
    base += f".{cls} tfoot td {{ font-weight: bold; border-top: 2px solid {c('text')}; }}\n"
    return base


def table_html(headers, rows, cls="tbl", num_cols=(), foot=None, caption=None, colgroup=None):
    o = [f'<table class="{cls}">']
    if caption:
        o.append(f"<caption>{esc(caption)}</caption>")
    if colgroup:
        o.append("<colgroup>" + "".join(f'<col style="width:{w}">' for w in colgroup) + "</colgroup>")
    nc = ' class="num"'

    def a(i):
        return nc if i in num_cols else ""
    o.append("<thead><tr>" + "".join(f"<th{a(i)}>{esc(h)}</th>" for i, h in enumerate(headers)) + "</tr></thead>")
    o.append("<tbody>")
    for row in rows:
        o.append("<tr>" + "".join(f"<td{a(i)}>{cell}</td>" for i, cell in enumerate(row)) + "</tr>")
    o.append("</tbody>")
    if foot:
        o.append("<tfoot><tr>" + "".join(f"<td{a(i)}>{cell}</td>" for i, cell in enumerate(foot)) + "</tr></tfoot>")
    o.append("</table>")
    return "\n".join(o)


def header_block(st, title, subtitle="", logo="", right=""):
    r = st.r
    c = st.c
    v = st.header_variant
    rad = f"border-radius: {st.radius}px;" if st.radius else ""
    if v in ("band", "gradient-band"):
        bg = st.bg_strong() if v == "gradient-band" else f"background: {c('primary')};"
        css = (f".doc-header {{ {bg} color: #fff; padding: {r.choice(['24px 28px', '28px 32px', '20px 24px', '1.5rem 2rem'])}; {rad} "
               f"display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}\n"
               f".doc-header h1 {{ color: #fff; margin: 0; }}\n.doc-header .sub {{ opacity: 0.85; margin-top: 4px; }}\n"
               f".doc-header .right {{ text-align: right; font-size: 0.9em; }}\n.doc-header .brand {{ display: flex; align-items: center; gap: 14px; }}\n")
    elif v == "split":
        css = (f".doc-header {{ display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 16px; "
               f"border-bottom: {r.choice(['3px', '2px', '4px'])} solid {c('primary')}; margin-bottom: 24px; }}\n"
               f".doc-header h1 {{ margin: 0; color: {c('primary')}; }}\n.doc-header .sub {{ color: {c('muted')}; margin-top: 4px; }}\n"
               f".doc-header .right {{ text-align: right; color: {c('muted')}; font-size: 0.9em; }}\n.doc-header .brand {{ display: flex; align-items: center; gap: 12px; }}\n")
    elif v == "centered":
        css = (f".doc-header {{ text-align: center; padding-bottom: 18px; margin-bottom: 24px; border-bottom: 1px solid {c('border')}; }}\n"
               f".doc-header h1 {{ margin: 8px 0 0; letter-spacing: 0.02em; }}\n.doc-header .sub {{ color: {c('muted')}; }}\n"
               f".doc-header .right {{ margin-top: 8px; font-size: 0.9em; color: {c('muted')}; }}\n.doc-header .brand {{ display: flex; flex-direction: column; align-items: center; }}\n")
    else:
        css = (f".doc-header {{ border-left: 6px solid {c('primary')}; padding: 8px 0 8px 18px; margin-bottom: 24px; display: flex; justify-content: space-between; }}\n"
               f".doc-header h1 {{ margin: 0; }}\n.doc-header .sub {{ color: {c('muted')}; }}\n.doc-header .right {{ text-align: right; font-size: 0.9em; }}\n"
               f".doc-header .brand {{ display: flex; align-items: center; gap: 12px; }}\n")
    html = (f'<header class="doc-header"><div class="brand">{logo}<div><h1>{esc(title)}</h1>'
            + (f'<div class="sub">{subtitle}</div>' if subtitle else "") + f"</div></div>"
            + (f'<div class="right">{right}</div>' if right else "") + "</header>")
    return html, css


def card_css(st, cls="card"):
    c = st.c
    bd = f"border: 1px solid {c('border')};" if (not st.shadow or st.r.random() < 0.4) else ""
    return (f".{cls} {{ background: #fff; {bd} border-radius: {st.radius}px; padding: {st.r.choice(['14px', '16px', '18px 20px', '1rem 1.25rem', '20px'])}; "
            f"{st.shadow_css(st.r.randint(0, 2))} break-inside: avoid; page-break-inside: avoid; }}\n")


def kpi_cards(st, items, cols=None, cls="kpi"):
    r = st.r
    c = st.c
    cols = cols or min(len(items), r.choice([2, 3, 4, 4]))
    layout = r.choice(["grid", "flex"])
    if layout == "grid":
        wrap = f".{cls}-row {{ display: grid; grid-template-columns: repeat({cols}, 1fr); gap: {r.choice(['12px', '16px', '1rem', '20px'])}; margin: 18px 0; }}\n"
    else:
        wrap = f".{cls}-row {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 18px 0; }}\n.{cls}-row > .{cls} {{ flex: 1 1 calc({100 // cols}% - 14px); }}\n"
    accent = r.choice(["top", "left", "none", "bg"])
    acc = {"top": f"border-top: 4px solid {c('primary')};", "left": f"border-left: 4px solid {c('accent')};", "none": "",
           "bg": f"background: {c('soft')};"}[accent]
    css = wrap + card_css(st, cls) + (f".{cls} {{ {acc} }}\n.{cls} .label {{ font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.06em; color: {c('muted')}; }}\n"
                                      f".{cls} .value {{ font-size: {r.choice(['1.6em', '1.8em', '2em', '22px', '26px'])}; font-weight: 700; color: {c('dark')}; margin: 4px 0; }}\n"
                                      f".{cls} .delta {{ font-size: 0.82em; }} .{cls} .up {{ color: #16a34a; }} .{cls} .down {{ color: #dc2626; }}\n")
    html = f'<div class="{cls}-row">' + "".join(
        f'<div class="{cls}"><div class="label">{esc(lab)}</div><div class="value">{esc(val)}</div>'
        + (f'<div class="delta {"up" if d >= 0 else "down"}">{"▲" if d >= 0 else "▼"} {abs(d):.1f}% {esc(note)}</div>' if d is not None else "")
        + (extra or "") + "</div>" for lab, val, d, note, extra in items) + "</div>"
    return html, css


def badge_css(st):
    return (".badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 0.75em; font-weight: 600; }\n"
            ".badge.ok { background: #dcfce7; color: #166534; } .badge.warn { background: #fef3c7; color: #92400e; }\n"
            ".badge.bad { background: #fee2e2; color: #991b1b; } .badge.info { background: #dbeafe; color: #1e40af; }\n")


def badge(kind, text):
    return f'<span class="badge {kind}">{esc(text)}</span>'


def fixed_footer(st, text):
    css = (f".fixed-footer {{ position: fixed; bottom: 0; left: 0; right: 0; text-align: center; font-size: 8pt; color: {st.c('muted')}; "
           f"border-top: 1px solid {st.c('border')}; padding-top: 4px; background: #fff; }}\n")
    return f'<div class="fixed-footer">{esc(text)}</div>', css


def callout(st, title, body):
    c = st.c
    kind = st.r.choice(["info", "note", "warn"])
    col = {"info": c("primary"), "note": c("accent"), "warn": "#d97706"}[kind]
    bg = {"info": c("soft"), "note": "#f8fafc", "warn": "#fffbeb"}[kind]
    css = (f".callout-{kind} {{ border-left: 4px solid {col}; background: {bg}; padding: 12px 16px; margin: 16px 0; "
           f"border-radius: 0 {st.radius}px {st.radius}px 0; break-inside: avoid; }}\n.callout-{kind} strong {{ color: {col}; display: block; margin-bottom: 4px; }}\n")
    return f'<div class="callout-{kind}"><strong>{esc(title)}</strong>{body}</div>', css


def svg_seal(st, text="OFFICIAL", size=110):
    c = st.p
    import math
    pts = []
    for k in range(48):
        a = 2 * math.pi * k / 48
        rr = size / 2 - (0 if k % 2 == 0 else 5)
        pts.append(f"{size / 2 + rr * math.cos(a):.1f},{size / 2 + rr * math.sin(a):.1f}")
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}"><polygon points="{" ".join(pts)}" fill="{c["accent"]}"/>'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2 - 12}" fill="none" stroke="#fff" stroke-width="2"/>'
            f'<text x="{size / 2}" y="{size / 2 + 5}" text-anchor="middle" font-size="{size / 8:.0f}" font-weight="bold" fill="#fff" font-family="Arial, sans-serif">{esc(text)}</text></svg>')


def check_icon(color, size=14):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" style="vertical-align:-2px"><circle cx="12" cy="12" r="11" fill="{color}"/>'
            f'<path d="M7 12.5l3.2 3.2L17 9" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')

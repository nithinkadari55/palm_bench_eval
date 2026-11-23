import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_i18n import INVOICE_LABELS, LANGS  # noqa: E402
from gen_lib import (CURRENCIES, GOODS, MONTHS, SERVICES, Prose, address, company, date, email, esc, html_doc,  # noqa: E402
                     iso_date, lorem, money, person, phone, svg_bar, svg_barcode, svg_line, svg_logo, svg_pie, svg_placeholder,
                     svg_qr, svg_spark)
from gen_parts import (SCRIPT_STACKS, Style, badge, badge_css, base_css, callout, card_css, check_icon, fixed_footer,  # noqa: E402
                       header_block, kpi_cards, page_css, svg_seal, table_css, table_html)

GEN_VERSION = "po-gen-1"
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
MON3 = [m[:3] for m in MONTHS]
REGIONS = ["North America", "EMEA", "APAC", "LATAM", "UK & Ireland", "DACH", "Nordics", "India", "Japan", "ANZ"]
DEPTS = ["Engineering", "Sales", "Marketing", "Finance", "Operations", "Support", "HR", "Legal", "Product", "Design"]
SKILLS = ["Python", "SQL", "TypeScript", "React", "AWS", "Kubernetes", "Figma", "Excel", "Tableau", "Go", "Rust", "Java",
          "Project management", "Stakeholder communication", "Data analysis", "Machine learning", "Public speaking", "Agile/Scrum",
          "Financial modeling", "Copywriting", "SEO", "Docker", "Terraform", "Power BI", "Negotiation", "C++", "Leadership"]
JOBS = ["Software Engineer", "Senior Data Analyst", "Product Manager", "UX Designer", "Marketing Manager", "Financial Analyst",
        "Operations Lead", "DevOps Engineer", "Customer Success Manager", "Research Scientist", "Account Executive", "Engineering Manager"]
UNIS = ["University of Michigan", "Imperial College London", "TU Munich", "University of Toronto", "IIT Bombay", "Stanford University",
        "University of Melbourne", "ETH Zurich", "National University of Singapore", "McGill University", "University of Edinburgh"]
DEGREES = ["B.Sc. Computer Science", "M.Sc. Data Science", "MBA", "B.A. Economics", "B.Eng. Mechanical Engineering", "M.A. Design",
           "Ph.D. Physics", "B.Sc. Mathematics", "M.Eng. Software Systems"]
DISHES = ["Grilled salmon", "Truffle risotto", "Margherita pizza", "Caesar salad", "Beef bourguignon", "Pad thai", "Chicken tikka masala",
          "Mushroom soup", "Lamb shank", "Fish tacos", "Caprese salad", "Ribeye steak", "Vegetable curry", "Lobster bisque",
          "Tiramisu", "Crème brûlée", "Chocolate fondant", "Lemon tart", "Burrata", "Seared scallops", "Duck confit", "Gnocchi al pesto"]
AIRPORTS = [("SFO", "San Francisco"), ("JFK", "New York"), ("LHR", "London"), ("CDG", "Paris"), ("FRA", "Frankfurt"), ("NRT", "Tokyo"),
            ("SIN", "Singapore"), ("DXB", "Dubai"), ("BLR", "Bengaluru"), ("SYD", "Sydney"), ("AMS", "Amsterdam"), ("YYZ", "Toronto"),
            ("MAD", "Madrid"), ("ORD", "Chicago"), ("HKG", "Hong Kong"), ("BOS", "Boston")]
AIRLINES = ["Skyward Air", "Oceanic Airlines", "Northstar Airways", "Aurora Air", "Meridian Airlines", "Pacific Crest"]
PRODUCTS = ["X200 Industrial Sensor", "AeroLite Drone Kit", "PowerCell 48V Battery", "NovaHub Smart Gateway", "FlowMax Pump 3000",
            "ClearView 4K Camera", "ThermoGuard Controller", "EcoCharge Wall Box", "SignalPro Router AX6", "TerraPrint 3D Printer"]


def fmt_money(v, cur):
    sym = cur[0]
    return money(v, sym, 0 if cur[1] == "JPY" else 2)


def rand_series(r, n, lo=20, hi=100, trend=0.0):
    v = r.uniform(lo, hi)
    out = []
    for _ in range(n):
        v = max(lo * 0.3, v * (1 + trend) + r.uniform(-(hi - lo) * 0.12, (hi - lo) * 0.12))
        out.append(round(v, 1))
    return out


def prose_paras(pr, n, lo=3, hi=6):
    return "".join(f"<p>{esc(pr.para(lo, hi))}</p>" for _ in range(n))


def chart(r, st, title=None, kind=None):
    kind = kind or r.choice(["bar", "bar", "line", "area", "pie", "donut", "hbar", "stacked"])
    p = st.p
    if kind in ("pie", "donut"):
        labs = r.sample(REGIONS, r.randint(3, 6))
        return svg_pie(r, p, labs, [r.randint(5, 60) for _ in labs], size=r.choice([180, 200, 220]), donut=kind == "donut", title=title)
    n = r.choice([4, 5, 6, 8, 12])
    labs = QUARTERS[:n] if n == 4 else MON3[:n] if n in (6, 8, 12) else [str(2019 + k) for k in range(n)]
    ns = r.choice([1, 1, 2, 3])
    names = r.sample(["Revenue", "Costs", "Profit", "Target", "Prior year", "Forecast", "Units", "Orders"], ns)
    series = [rand_series(r, n, 20, r.choice([100, 500, 2000, 12000])) for _ in range(ns)]
    if kind in ("line", "area"):
        return svg_line(r, p, labs, series, names if ns > 1 else None, area=kind == "area", title=title)
    return svg_bar(r, p, labs, series, names if ns > 1 else None, horizontal=kind == "hbar", stacked=kind == "stacked" and ns > 1, title=title)


def figure(r, st, cap, svg):
    return f'<figure class="fig">{svg}<figcaption>{esc(cap)}</figcaption></figure>'


def fig_css(st):
    return (f".fig {{ margin: 18px 0; break-inside: avoid; page-break-inside: avoid; text-align: center; }}\n"
            f".fig svg {{ max-width: 100%; height: auto; }}\n.fig figcaption {{ font-size: 0.85em; color: {st.c('muted')}; margin-top: 6px; }}\n")


# ----------------------------------------------------------------------------- invoices / receipts / quotes

def g_invoice(r, i, kind="invoice"):
    st = Style(r)
    lang = "en" if kind != "invoice" else r.choice(["en"] * 6 + ["de", "fr", "es"])
    L = dict(INVOICE_LABELS[lang])
    if kind == "quote":
        L.update(invoice=r.choice(["Quote", "Quotation", "Estimate", "Proposal"]), no="Quote #", due="Valid Until", date="Date",
                 thanks="We look forward to working with you.")
    cur = r.choice(CURRENCIES)
    seller, buyer = company(r), company(r)
    n_items = r.choice([2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 24, 35, 50])
    pool = SERVICES + GOODS
    items = []
    for _ in range(n_items):
        q = r.choice([1, 1, 1, 2, 3, 4, 5, 10, 12, 20, 40])
        pr_ = round(r.uniform(8, 2400) * (100 if cur[1] == "JPY" else 1), 2)
        items.append((r.choice(pool), q, pr_))
    sub = sum(q * p for _, q, p in items)
    disc = round(sub * r.choice([0, 0, 0, 0.05, 0.1]), 2)
    tax_rate = r.choice([0, 5, 7.5, 8.25, 10, 13, 18, 19, 20, 21])
    tax = round((sub - disc) * tax_rate / 100, 2)
    total = sub - disc + tax
    no = f"{r.choice(['INV', 'Q', 'EST', '#', 'F'])}-{r.randint(2023, 2025)}-{r.randint(1, 9999):04d}"
    logo = svg_logo(r, st.p, seller, r.choice([40, 44, 52])) if r.random() < 0.8 else ""
    meta = (f"<div><strong>{esc(L['no'])}</strong> {esc(no)}</div><div><strong>{esc(L['date'])}</strong> {esc(date(r))}</div>"
            f"<div><strong>{esc(L['due'])}</strong> {esc(date(r))}</div>")
    hdr, hcss = header_block(st, L["invoice"].upper() if r.random() < 0.4 else L["invoice"], esc(seller), logo, meta)
    a1, a2 = address(r), address(r)
    pname = person(r)
    parties = (f'<section class="parties"><div class="party"><h3>{esc(L["bill_to"])}</h3><p><strong>{esc(buyer)}</strong><br>{esc(pname)}<br>'
               + "<br>".join(esc(x) for x in a2) + f'<br>{esc(email(r, pname, buyer))}</p></div>'
               f'<div class="party"><h3>From</h3><p><strong>{esc(seller)}</strong><br>' + "<br>".join(esc(x) for x in a1)
               + f'<br>{esc(phone(r))}<br>VAT {r.randint(10 ** 8, 10 ** 9 - 1)}</p></div>'
               + (f'<div class="party"><h3>{esc(L["ship_to"])}</h3><p>' + "<br>".join(esc(x) for x in address(r)) + "</p></div>" if r.random() < 0.35 else "")
               + "</section>")
    rows = [[str(k + 1), esc(d) + (f'<div class="desc-sub">{esc(lorem(r, r.randint(4, 10)))}</div>' if r.random() < 0.3 else ""),
             str(q), fmt_money(p, cur), fmt_money(q * p, cur)] for k, (d, q, p) in enumerate(items)]
    tbl = table_html(["#", L["desc"], L["qty"], L["price"], L["amount"]], rows, num_cols=(2, 3, 4), colgroup=["6%", "52%", "10%", "16%", "16%"])
    trows = [(L["subtotal"], fmt_money(sub, cur))]
    if disc:
        trows.append((L["discount"], "-" + fmt_money(disc, cur)))
    trows.append((f"{L['tax']} ({tax_rate}%)", fmt_money(tax, cur)))
    totals = ('<div class="totals-wrap"><table class="totals">' + "".join(f"<tr><td>{esc(a)}</td><td class=\"num\">{esc(b)}</td></tr>" for a, b in trows)
              + f'<tr class="grand"><td>{esc(L["total"])} ({cur[1]})</td><td class="num">{esc(fmt_money(total, cur))}</td></tr></table></div>')
    notes = (f'<section class="notes"><h3>{esc(L["notes"])}</h3><p>{esc(Prose(r).para(1, 3))}</p>'
             f'<h3>{esc(L["terms"])}</h3><p>{esc(r.choice(["Net 30", "Net 15", "Due on receipt", "50% upfront, 50% on delivery", "Net 45"]))}. '
             f'IBAN DE{r.randint(10, 99)} {r.randint(1000, 9999)} {r.randint(1000, 9999)} {r.randint(1000, 9999)} {r.randint(10, 99)} · SWIFT {r.choice(["DEUTDEFF", "BOFAUS3N", "BARCGB22", "HSBCSGSG"])}</p></section>')
    extra = ""
    if kind == "quote":
        extra = ('<section class="accept"><h3>Acceptance</h3><p>By signing below, the client accepts this quotation and its terms.</p>'
                 '<div class="sigs"><div class="sig">Authorized signature</div><div class="sig">Date</div></div></section>')
    stamp = ""
    if kind == "invoice" and r.random() < 0.2:
        stamp = f'<div class="stamp">{r.choice(["PAID", "OVERDUE", "DRAFT"])}</div>'
    qr = f'<div class="qr">{svg_qr(r, 21, 3)}<div>Scan to pay</div></div>' if r.random() < 0.25 else ""
    foot = f'<footer class="thanks">{esc(L["thanks"])}</footer>'
    c = st.c
    css = base_css(st, page_css(st, r, f"{L['invoice']} {no}"), "".join([
        hcss, table_css(st), fig_css(st),
        ".parties { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin-bottom: 24px; }\n",
        f".party h3 {{ font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.08em; color: {c('muted')}; margin: 0 0 6px; }}\n.party p {{ margin: 0; }}\n",
        f".desc-sub {{ font-size: 0.85em; color: {c('muted')}; }}\n",
        ".totals-wrap { display: flex; justify-content: flex-end; margin-top: 16px; break-inside: avoid; }\n",
        f".totals {{ width: {r.choice(['280px', '45%', '320px', '40%'])}; border-collapse: collapse; }}\n.totals td {{ padding: 6px 8px; }}\n",
        ".totals .num { text-align: right; }\n",
        f".totals .grand td {{ font-weight: 700; font-size: 1.15em; border-top: 2px solid {c('primary')}; color: {c('dark')}; "
        + (f"background: {c('soft')};" if r.random() < 0.5 else "") + " }\n",
        f".notes {{ margin-top: 28px; font-size: 0.9em; color: {c('muted')}; break-inside: avoid; }}\n.notes h3 {{ font-size: 0.95em; margin: 12px 0 4px; color: {c('text')}; }}\n",
        ".accept { margin-top: 24px; break-inside: avoid; } .sigs { display: flex; gap: 40px; margin-top: 40px; }\n",
        f".sig {{ flex: 1; border-top: 1px solid {c('text')}; padding-top: 6px; font-size: 0.85em; color: {c('muted')}; }}\n",
        ".stamp { position: absolute; top: 160px; right: 60px; transform: rotate(-14deg); border: 4px solid #dc2626; color: #dc2626; "
        "font-size: 36px; font-weight: 800; padding: 4px 18px; border-radius: 8px; opacity: 0.75; letter-spacing: 0.1em; }\n",
        ".qr { float: right; text-align: center; font-size: 0.75em; margin-top: 12px; }\n",
        f".thanks {{ margin-top: 30px; text-align: center; color: {c('primary')}; font-weight: 600; }}\n",
        "body { position: relative; }\n" if stamp else "",
    ]))
    body = hdr + parties + tbl + totals + qr + notes + extra + stamp + foot
    if r.random() < 0.3:
        wrap_w = r.choice(["800px", "720px", "100%"])
        css += f".page {{ max-width: {wrap_w}; margin: 0 auto; }}\n"
        body = f'<div class="page">{body}</div>'
    return dict(title=f"{L['invoice']} {no}", css=css, body=body, lang=lang)


def g_quote(r, i):
    return g_invoice(r, i, "quote")


def g_receipt(r, i):
    st = Style(r, serif=False, base=r.choice(["10pt", "11px", "12px", "13px", "9pt"]))
    mono = r.random() < 0.55
    store = company(r)
    cur = r.choice(CURRENCIES[:4])
    items = [(r.choice(GOODS + DISHES), r.randint(1, 4), round(r.uniform(1, 120), 2)) for _ in range(r.randint(3, 22))]
    sub = sum(q * p for _, q, p in items)
    tax = round(sub * 0.08, 2)
    tip = round(sub * r.choice([0, 0, 0.15, 0.18, 0.2]), 2)
    thermal = r.random() < 0.45
    if thermal:
        pg = f"@page {{ size: {r.choice(['80mm 297mm', '80mm 200mm', '58mm 210mm', '3.15in 11in'])}; margin: {r.choice(['4mm', '5mm 3mm', '3mm'])}; }}\n"
    else:
        pg = page_css(st, r, none_prob=0.4)
    c = st.c
    rows = "".join(f'<div class="line"><span class="it">{q} × {esc(d)}</span><span class="amt">{fmt_money(q * p, cur)}</span></div>' for d, q, p in items)
    tots = [("Subtotal", sub), ("Tax 8%", tax)] + ([("Tip", tip)] if tip else []) + [("TOTAL", sub + tax + tip)]
    trs = "".join(f'<div class="line{" grand" if k == "TOTAL" else ""}"><span>{k}</span><span class="amt">{fmt_money(v, cur)}</span></div>' for k, v in tots)
    body = (f'<div class="receipt"><div class="center"><div class="store">{esc(store.upper())}</div><div>' + "<br>".join(esc(x) for x in address(r))
            + f'</div><div>{esc(phone(r))}</div></div><div class="sep"></div><div class="meta"><span>{esc(iso_date(r))} {r.randint(7, 22):02d}:{r.randint(0, 59):02d}</span>'
            f'<span>#{r.randint(10000, 99999)}</span></div><div class="meta"><span>Cashier: {esc(person(r).split()[0])}</span><span>Reg {r.randint(1, 9)}</span></div>'
            f'<div class="sep"></div>{rows}<div class="sep"></div>{trs}<div class="sep"></div>'
            f'<div class="center">Paid by {r.choice(["VISA ****", "Mastercard ****", "AMEX ****"])}{r.randint(1000, 9999)}<br>'
            f'{esc(r.choice(["Thank you for shopping with us!", "Thank you! Please come again.", "Returns accepted within 30 days with receipt."]))}</div>'
            f'<div class="center bc">{svg_barcode(r, 200, 48, str(r.randint(10 ** 11, 10 ** 12 - 1)))}</div></div>')
    width = "100%" if thermal else r.choice(["320px", "80mm", "360px", "300px"])
    css = base_css(st, pg, (
        f".receipt {{ width: {width}; margin: 0 auto; {'font-family: ' + st.mono + ';' if mono else ''} "
        + ("" if thermal else f"border: 1px solid {c('border')}; padding: 18px; border-radius: {st.radius}px; {st.shadow_css(1)}") + " }\n"
        ".center { text-align: center; } .store { font-size: 1.4em; font-weight: 800; letter-spacing: 0.08em; margin-bottom: 4px; }\n"
        f".sep {{ border-top: 1px {r.choice(['dashed', 'dotted', 'dashed'])} {c('text')}; margin: 8px 0; }}\n"
        ".line, .meta { display: flex; justify-content: space-between; gap: 8px; } .line .it { flex: 1; }\n"
        ".amt { white-space: nowrap; } .grand { font-weight: 800; font-size: 1.2em; margin-top: 4px; } .bc { margin-top: 10px; }\n"))
    return dict(title=f"Receipt {store}", css=css, body=body)


# ----------------------------------------------------------------------------- reports

def toc_html(st, entries):
    css = (f".toc ol {{ list-style: none; padding: 0; margin: 0; }}\n.toc li {{ display: flex; align-items: baseline; gap: 6px; padding: 4px 0; }}\n"
           f".toc li .dots {{ flex: 1; border-bottom: 1px dotted {st.c('muted')}; transform: translateY(-4px); }}\n")
    html = '<nav class="toc"><h2>Contents</h2><ol>' + "".join(
        f'<li><span>{k + 1}. {esc(t)}</span><span class="dots"></span><span>{pg}</span></li>' for k, (t, pg) in enumerate(entries)) + "</ol></nav>"
    return html, css


def g_report(r, i):
    st = Style(r)
    pr = Prose(r, "business")
    co = company(r)
    year = r.randint(2022, 2025)
    q = r.choice(QUARTERS + ["FY", "H1", "H2"])
    title = r.choice([f"{q} {year} Business Review", f"Annual Report {year}", f"{co} Performance Report", f"Market Analysis {year}",
                      f"Operational Review — {q} {year}", f"Sales Performance Report {q} {year}", f"Strategic Plan {year}–{year + 2}"])
    nsec = r.randint(3, 9)
    secs = [pr.title(2, 4) for _ in range(nsec)]
    c = st.c
    cover = r.random() < 0.55
    parts, css_parts = [], [table_css(st), fig_css(st), badge_css(st)]
    if cover:
        css_parts.append(f".cover {{ height: {r.choice(['250mm', '240mm', '900px', '260mm'])}; display: flex; flex-direction: column; justify-content: center; "
                         f"{st.bg_strong()} color: #fff; padding: 48px; border-radius: {st.radius}px; break-after: page; page-break-after: always; }}\n"
                         ".cover h1 { color: #fff; font-size: 3em; margin: 0 0 12px; } .cover .meta { margin-top: 40px; opacity: 0.9; }\n")
        parts.append(f'<section class="cover">{svg_logo(r, st.p, co, 64)}<h1>{esc(title)}</h1><div class="sub">{esc(co)}</div>'
                     f'<div class="meta">Prepared by {esc(person(r))}<br>{esc(date(r, year, year))}<br>{r.choice(["Confidential", "Internal use only", "Public"])}</div></section>')
        if r.random() < 0.6:
            th, tc = toc_html(st, [(s, 2 + k * r.randint(1, 2)) for k, s in enumerate(secs)])
            parts.append(th + '<div class="pb"></div>')
            css_parts.append(tc)
    else:
        h, hc = header_block(st, title, esc(co), svg_logo(r, st.p, co, 44), esc(date(r, year, year)))
        parts.append(h)
        css_parts.append(hc)
    css_parts.append(".pb { break-after: page; page-break-after: always; }\n")
    kitems = [(lab, val, r.uniform(-12, 25), r.choice(["vs last quarter", "YoY", "vs target", ""]), None) for lab, val in
              [("Revenue", f"${r.randint(2, 900)}.{r.randint(0, 9)}M"), ("Gross margin", f"{r.randint(20, 80)}.{r.randint(0, 9)}%"),
               ("Active customers", f"{r.randint(1, 900):,},{r.randint(100, 999)}"), ("NPS", str(r.randint(10, 80))),
               ("Churn", f"{r.uniform(0.5, 9):.1f}%"), ("EBITDA", f"${r.randint(1, 90)}.{r.randint(0, 9)}M")]][:r.choice([3, 4, 4, 6])]
    kh, kc = kpi_cards(st, kitems)
    css_parts.append(kc)
    parts.append(f'<h2>Executive Summary</h2>{prose_paras(pr, r.randint(1, 3))}{kh}')
    brk = r.random() < 0.35
    for k, s in enumerate(secs):
        sec = [f'<section class="sec"><h2>{k + 1}. {esc(s)}</h2>', prose_paras(pr, r.randint(1, 4))]
        roll = r.random()
        if roll < 0.35:
            sec.append(figure(r, st, f"Figure {k + 1}: {pr.title(2, 4)}", chart(r, st)))
        elif roll < 0.65:
            nrow = r.randint(4, 18)
            sel = r.sample(REGIONS + DEPTS, min(nrow, 20))
            rows = []
            for nm in sel:
                a, b = r.uniform(100, 9000), r.uniform(100, 9000)
                ch = (b - a) / a * 100
                rows.append([esc(nm), f"{a:,.0f}", f"{b:,.0f}", f'<span class="{"up" if ch >= 0 else "down"}">{ch:+.1f}%</span>',
                             badge(r.choice(["ok", "warn", "bad", "info"]), r.choice(["On track", "At risk", "Behind", "Ahead"]))])
            sec.append(table_html(["Segment", f"{year - 1}", f"{year}", "Change", "Status"], rows, num_cols=(1, 2, 3)))
        elif roll < 0.8:
            cb, cc = callout(st, r.choice(["Key takeaway", "Note", "Recommendation", "Risk"]), f"<p>{esc(pr.para(1, 2))}</p>")
            sec.append(cb)
            css_parts.append(cc)
        else:
            sec.append(f'<div class="two">{figure(r, st, "Breakdown", chart(r, st, kind=r.choice(["pie", "donut"])))}'
                       f'<div><h3>{esc(pr.title())}</h3><ul>' + "".join(f"<li>{esc(pr.sentence())}</li>" for _ in range(r.randint(3, 6))) + "</ul></div></div>")
        if r.random() < 0.4:
            sec.append(prose_paras(pr, r.randint(1, 3)))
        sec.append("</section>")
        parts.append("".join(sec))
    parts.append(f'<h2>Outlook</h2>{prose_paras(pr, r.randint(1, 3))}')
    css_parts.append(f".up {{ color: #16a34a; }} .down {{ color: #dc2626; }}\n.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }}\n"
                     f".sec h2 {{ color: {c('primary')}; border-bottom: 1px solid {c('border')}; padding-bottom: 6px; }}\n"
                     + (".sec { break-before: page; page-break-before: always; }\n.sec:first-of-type { break-before: auto; }\n" if brk else "")
                     + "h2, h3 { break-after: avoid; page-break-after: avoid; }\np { orphans: 3; widows: 3; text-align: " + r.choice(["left", "justify"]) + "; }\n")
    if r.random() < 0.12:
        fh, fc = fixed_footer(st, f"{co} · {title} · Confidential")
        parts.append(fh)
        css_parts.append(fc)
    css = base_css(st, page_css(st, r, title, numbers=0.75), "".join(css_parts))
    return dict(title=title, css=css, body="\n".join(parts))


# ----------------------------------------------------------------------------- resume

def g_resume(r, i):
    st = Style(r, base=r.choice(["10pt", "10.5pt", "11pt", "13px", "14px"]))
    name = person(r)
    job = r.choice(JOBS)
    c = st.c
    pr = Prose(r, "business")
    layout = r.choice(["sidebar", "sidebar", "single", "header-grid"])
    contact = [email(r, name, "mail co"), phone(r), f"{r.choice(['linkedin.com/in/', 'github.com/'])}{name.split()[0].lower()}{r.randint(1, 99)}",
               r.choice(address(r)[1:])]
    skills = r.sample(SKILLS, r.randint(6, 12))
    exps = []
    y = 2025
    for _ in range(r.randint(2, 5)):
        y0 = y - r.randint(1, 4)
        bullets = "".join(f"<li>{esc(pr.sentence())}</li>" for _ in range(r.randint(2, 5)))
        exps.append(f'<div class="job"><div class="job-h"><div><strong>{esc(r.choice(JOBS))}</strong> · {esc(company(r))}</div>'
                    f'<div class="when">{r.choice(MON3)} {y0} – {"Present" if y == 2025 else r.choice(MON3) + " " + str(y)}</div></div><ul>{bullets}</ul></div>')
        y = y0
    edu = "".join(f'<div class="edu"><strong>{esc(r.choice(DEGREES))}</strong><br>{esc(r.choice(UNIS))} · {y - r.randint(0, 6)}</div>' for _ in range(r.randint(1, 2)))
    bars = r.random() < 0.5
    if bars:
        sk = "".join(f'<div class="skill"><span>{esc(s)}</span><div class="bar"><div style="width:{r.randint(45, 98)}%"></div></div></div>' for s in skills)
    else:
        sk = '<div class="tags">' + "".join(f'<span class="tag">{esc(s)}</span>' for s in skills) + "</div>"
    langs = "".join(f"<li>{lang} — {lvl}</li>" for lang, lvl in r.sample([("English", "Native"), ("Spanish", "Professional"), ("German", "B2"),
                                                                        ("French", "Conversational"), ("Hindi", "Native"), ("Mandarin", "Basic")], r.randint(1, 3)))
    summary = f'<section><h2>Profile</h2><p>{esc(pr.para(2, 3))}</p></section>'
    exp = f'<section><h2>Experience</h2>{"".join(exps)}</section>'
    side = (f'<section><h2>Contact</h2><ul class="plain">' + "".join(f"<li>{esc(x)}</li>" for x in contact) + "</ul></section>"
            f'<section><h2>Skills</h2>{sk}</section><section><h2>Education</h2>{edu}</section><section><h2>Languages</h2><ul class="plain">{langs}</ul></section>')
    proj = ""
    if r.random() < 0.5:
        proj = "<section><h2>Projects</h2>" + "".join(f'<div class="proj"><strong>{esc(pr.title(2, 3))}</strong> — {esc(pr.sentence())}</div>' for _ in range(r.randint(2, 4))) + "</section>"
    common = (f"h2 {{ font-size: 0.95em; text-transform: uppercase; letter-spacing: 0.12em; color: {c('primary')}; margin: 18px 0 8px; "
              f"border-bottom: {r.choice(['1px', '2px'])} solid {c('border')}; padding-bottom: 4px; }}\n"
              ".job { margin-bottom: 12px; break-inside: avoid; } .job-h { display: flex; justify-content: space-between; gap: 12px; }\n"
              f".when {{ color: {c('muted')}; white-space: nowrap; font-size: 0.9em; }} .job ul {{ margin: 4px 0 0; padding-left: 18px; }}\n"
              ".plain { list-style: none; padding: 0; margin: 0; } .plain li { margin-bottom: 3px; }\n"
              ".skill { margin-bottom: 6px; font-size: 0.9em; } .bar { height: 6px; background: rgba(0,0,0,0.12); border-radius: 3px; margin-top: 2px; }\n"
              f".bar > div {{ height: 100%; background: {c('accent')}; border-radius: 3px; }}\n"
              f".tags {{ display: flex; flex-wrap: wrap; gap: 6px; }} .tag {{ padding: 2px 10px; border-radius: 999px; background: {c('soft')}; color: {c('dark')}; font-size: 0.85em; }}\n"
              ".edu, .proj { margin-bottom: 8px; }\n")
    namebl = f'<h1 class="name">{esc(name)}</h1><div class="role">{esc(job)}</div>'
    if layout == "sidebar":
        side_left = r.random() < 0.7
        body = (f'<div class="cv"><aside class="side">{namebl if side_left else ""}{side}</aside><main class="main">{"" if side_left else namebl}{summary}{exp}{proj}</main></div>')
        side_dark = r.random() < 0.4
        css_x = (f".cv {{ display: grid; grid-template-columns: {r.choice(['32%', '35%', '230px', '1fr'])} {'2fr' if r.random() < 0.3 else '1fr'}; gap: 28px; }}\n"
                 f".side {{ background: {c('dark') if side_dark else c('soft')}; padding: 22px 18px; border-radius: {st.radius}px; }}\n"
                 f".name {{ font-size: 2em; margin: 0; }} .role {{ color: {c('accent')}; font-weight: 600; margin-bottom: 10px; }}\n")
        if side_dark:
            css_x += ".side, .side h2, .side .name { color: #fff; } .side h2 { border-color: rgba(255,255,255,0.3); } .side .tag { background: rgba(255,255,255,0.15); color: #fff; }\n"
    elif layout == "header-grid":
        body = (f'<header class="top">{namebl}<div class="contact">' + " · ".join(esc(x) for x in contact) + "</div></header>"
                f'<div class="cols"><main>{summary}{exp}{proj}</main><aside>{side.split("</section>", 1)[1]}</aside></div>')
        css_x = (f".top {{ {st.bg_strong()} color: #fff; padding: 24px 28px; border-radius: {st.radius}px; }} .top .name {{ color: #fff; margin: 0; }}\n"
                 ".top .role { opacity: 0.9; font-size: 1.1em; } .top .contact { margin-top: 8px; font-size: 0.9em; }\n"
                 ".cols { display: flex; gap: 28px; } .cols main { flex: 2; } .cols aside { flex: 1; }\n")
    else:
        body = (f'<header class="top">{namebl}<div class="contact">' + " | ".join(esc(x) for x in contact) + f"</div></header>{summary}{exp}{proj}"
                f'<div class="grid2">{side.split("</section>", 1)[1]}</div>')
        css_x = (f".top {{ text-align: {r.choice(['center', 'left'])}; border-bottom: 3px solid {c('primary')}; padding-bottom: 10px; }}\n"
                 ".top .name { margin: 0; letter-spacing: 0.04em; } .top .contact { font-size: 0.9em; margin-top: 4px; }\n"
                 ".grid2 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }\n")
    css = base_css(st, page_css(st, r, none_prob=0.3, numbers=0.2, margins=["12mm", "15mm", "0.5in", "10mm 12mm", "18mm"]), common + css_x)
    return dict(title=f"{name} — Resume", css=css, body=body)


# ----------------------------------------------------------------------------- contract

def g_contract(r, i):
    st = Style(r, serif=r.random() < 0.6, base=r.choice(["10.5pt", "11pt", "12pt", "11pt", "14px"]))
    pr = Prose(r, "legal")
    a, b = company(r), company(r)
    kind = r.choice(["Master Services Agreement", "Non-Disclosure Agreement", "Software License Agreement", "Commercial Lease Agreement",
                     "Consulting Agreement", "Data Processing Agreement", "Employment Agreement", "Supply Agreement"])
    c = st.c
    nclause = r.randint(8, 30)
    counters = r.random() < 0.5
    heads = ["Definitions", "Scope of Services", "Term and Termination", "Fees and Payment", "Confidentiality", "Intellectual Property",
             "Warranties", "Limitation of Liability", "Indemnification", "Insurance", "Data Protection", "Force Majeure", "Assignment",
             "Notices", "Governing Law", "Dispute Resolution", "Non-Solicitation", "Audit Rights", "Subcontracting", "Entire Agreement",
             "Severability", "Amendments", "Waiver", "Counterparts", "Publicity", "Compliance", "Records", "Survival", "Relationship", "Costs"]
    clauses = []
    for k in range(nclause):
        h = heads[k % len(heads)]
        subs = []
        for s in range(r.randint(1, 6)):
            num = "" if counters else f'<span class="n">{k + 1}.{s + 1}</span> '
            txt = pr.para(1, 3)
            if r.random() < 0.15:
                txt += " " + "; ".join(f"({chr(97 + j)}) {pr.sentence()[:-1]}" for j in range(r.randint(2, 4))) + "."
            subs.append(f'<p class="sub">{num}{esc(txt)}</p>')
        title_num = "" if counters else f"{k + 1}. "
        clauses.append(f'<section class="clause"><h2>{title_num}{esc(h)}</h2>{"".join(subs)}</section>')
    sig = ('<section class="sign"><p>IN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.</p><div class="sig-grid">'
           + "".join(f'<div class="sig-box"><div class="party">{esc(x)}</div><div class="line"></div><div>Name: {esc(person(r))}</div>'
                     f'<div>Title: {esc(r.choice(["CEO", "Director", "General Counsel", "CFO", "Managing Partner"]))}</div><div>Date: ____________</div></div>' for x in (a, b))
           + "</div></section>")
    intro = (f'<h1>{esc(kind)}</h1><p class="parties">This {esc(kind)} (the "Agreement") is entered into as of {esc(date(r))} (the "Effective Date") by and between '
             f'<strong>{esc(a)}</strong>, a company with offices at {esc(", ".join(address(r)))} ("Party A"), and <strong>{esc(b)}</strong>, '
             f'with offices at {esc(", ".join(address(r)))} ("Party B").</p><h3>Recitals</h3>'
             + "".join(f"<p>{chr(65 + j)}. WHEREAS, {esc(pr.sentence())}</p>" for j in range(r.randint(2, 4))) + "<p>NOW, THEREFORE, the Parties agree as follows:</p>")
    sched = ""
    if r.random() < 0.4:
        rows = [[esc(r.choice(SERVICES)), esc(r.choice(["Monthly", "One-off", "Quarterly", "Per hour"])), money(r.uniform(500, 50000))] for _ in range(r.randint(4, 12))]
        sched = f'<section class="schedule"><h2>Schedule A — Fees</h2>{table_html(["Service", "Billing", "Fee"], rows, num_cols=(2,))}</section>'
    cnt_css = ""
    if counters:
        cnt_css = ("body { counter-reset: clause; } .clause { counter-reset: sub; } .clause h2::before { counter-increment: clause; content: counter(clause) \". \"; }\n"
                   ".clause .sub::before { counter-increment: sub; content: counter(clause) \".\" counter(sub) \" \"; font-weight: bold; margin-right: 4px; }\n")
    css = base_css(st, page_css(st, r, kind, numbers=0.9, none_prob=0.05), (
        table_css(st) + cnt_css
        + f"h1 {{ text-align: center; text-transform: uppercase; letter-spacing: 0.06em; font-size: 1.6em; border-bottom: 2px solid {c('text')}; padding-bottom: 10px; }}\n"
        + "h2 { font-size: 1.05em; margin: 18px 0 6px; break-after: avoid; page-break-after: avoid; }\n"
        + f".sub {{ text-align: justify; margin: 0 0 8px; {r.choice(['', 'padding-left: 2em; text-indent: -2em;', 'margin-left: 1em;'])} }}\n.n {{ font-weight: bold; }}\n"
        + ".sign { break-inside: avoid; page-break-inside: avoid; margin-top: 30px; } .sig-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }\n"
        + f".sig-box .line {{ border-bottom: 1px solid {c('text')}; height: 48px; margin-bottom: 6px; }} .sig-box .party {{ font-weight: bold; }}\n"
        + (".schedule { break-before: page; page-break-before: always; }\n" if r.random() < 0.5 else "")
        + "p { orphans: 2; widows: 2; }\n"))
    return dict(title=kind, css=css, body=intro + "".join(clauses) + sig + sched)


# ----------------------------------------------------------------------------- academic paper

def g_paper(r, i):
    st = Style(r, serif=r.random() < 0.7, base=r.choice(["10pt", "9.5pt", "10pt", "11pt", "13px"]))
    pr = Prose(r, "academic")
    c = st.c
    title = pr.title(4, 9)
    authors = [person(r) for _ in range(r.randint(1, 6))]
    affs = r.sample(UNIS, r.randint(1, min(3, len(authors))))
    auth = ", ".join(f"{esc(a)}<sup>{r.randint(1, len(affs))}</sup>" for a in authors)
    aff = "<br>".join(f"<sup>{k + 1}</sup>{esc(u)}" for k, u in enumerate(affs))
    secs = ["Introduction", "Related Work", "Method", "Experiments", "Results", "Discussion", "Conclusion"]
    if r.random() < 0.4:
        secs = secs[:3] + ["Theoretical Analysis"] + secs[3:]
    body = []
    nref = r.randint(8, 40)
    figs = 0
    for k, s in enumerate(secs):
        body.append(f"<h2>{k + 1}&nbsp;&nbsp;{s}</h2>")
        for _ in range(r.randint(2, 5)):
            p_ = pr.para(3, 6)
            cites = ", ".join(str(r.randint(1, nref)) for _ in range(r.randint(1, 3)))
            body.append(f"<p>{esc(p_)} [{cites}]</p>")
        if r.random() < 0.3:
            body.append(f'<h3>{k + 1}.1&nbsp;&nbsp;{esc(pr.title(2, 4))}</h3><p>{esc(pr.para(2, 4))}</p>')
        if s in ("Method", "Theoretical Analysis") and r.random() < 0.7:
            body.append(f'<div class="eq">L(θ) = Σ<sub>i=1</sub><sup>N</sup> ‖ f<sub>θ</sub>(x<sub>i</sub>) − y<sub>i</sub> ‖<sup>2</sup> + λ ‖θ‖<sub>1</sub> <span class="eqn">({k + 1})</span></div>')
        if s in ("Experiments", "Results") or r.random() < 0.2:
            figs += 1
            span = r.random() < 0.3
            if r.random() < 0.5:
                models = ["Baseline", "ResNet-50", "ViT-B/16", "BERT-base", "Ours (small)", "Ours (large)", "LSTM", "GPT-2", "T5"]
                ms = r.sample(models, r.randint(3, 7))
                rows = [[esc(m)] + [f"{r.uniform(40, 95):.1f}" for _ in range(3)] for m in ms]
                body.append(f'<div class="tblfig{" span" if span else ""}"><div class="cap">Table {figs}: {esc(pr.title(3, 6))}</div>'
                            + table_html(["Model", "Acc.", "F1", "BLEU"], rows, num_cols=(1, 2, 3), cls="atbl") + "</div>")
            else:
                body.append(f'<figure class="afig{" span" if span else ""}">{chart(r, st, kind=r.choice(["line", "bar"]))}'
                            f"<figcaption>Figure {figs}: {esc(pr.sentence())}</figcaption></figure>")
    refs = "".join(f'<li>{esc(person(r).split()[-1])}, {esc(person(r)[0])}., and {esc(person(r).split()[-1])}, {esc(person(r)[0])}. '
                   f'{esc(pr.title(3, 7))}. <em>{r.choice(["NeurIPS", "ICML", "ACL", "CVPR", "Nature", "JMLR", "arXiv preprint", "ICLR", "EMNLP"])}</em>, '
                   f'{r.randint(1998, 2025)}.</li>' for _ in range(nref))
    cols = r.choice([2, 2, 2, 1])
    css = base_css(st, page_css(st, r, none_prob=0.25, numbers=0.7, margins=["18mm", "20mm 16mm", "0.75in", "1in", "15mm"]), (
        ".title { text-align: center; font-size: 1.7em; margin: 0 0 10px; } .authors { text-align: center; } .affs { text-align: center; font-size: 0.85em; color: #555; margin-bottom: 14px; }\n"
        f".abstract {{ margin: 0 {r.choice(['6%', '10%', '0'])} 18px; font-size: 0.92em; text-align: justify; "
        + (f"background: {c('soft')}; padding: 10px 14px;" if r.random() < 0.3 else "") + " }\n.abstract strong { display: block; text-align: center; margin-bottom: 4px; }\n"
        + (f".body {{ column-count: {cols}; column-gap: {r.choice(['24px', '0.3in', '20px', '8mm'])}; "
           + (f"column-rule: 1px solid {c('border')};" if r.random() < 0.2 else "") + " }\n" if cols > 1 else "")
        + "h2 { font-size: 1.15em; margin: 14px 0 6px; break-after: avoid; } h3 { font-size: 1em; font-style: italic; }\n"
        + "p { text-align: justify; margin: 0 0 6px; " + r.choice(["", "text-indent: 1.2em;"]) + " hyphens: auto; }\n"
        + ".eq { text-align: center; margin: 10px 0; font-style: italic; position: relative; } .eqn { position: absolute; right: 0; font-style: normal; }\n"
        + ".afig, .tblfig { margin: 10px 0; break-inside: avoid; text-align: center; } .afig svg { width: 100%; height: auto; }\n"
        + ".span { column-span: all; } figcaption, .cap { font-size: 0.85em; margin: 4px 0; }\n"
        + ".atbl { width: 100%; border-collapse: collapse; font-size: 0.9em; } .atbl th, .atbl td { padding: 3px 6px; } .atbl .num { text-align: right; }\n"
        + ".atbl thead th { border-top: 1.5px solid #000; border-bottom: 1px solid #000; } .atbl tbody tr:last-child td { border-bottom: 1.5px solid #000; }\n"
        + ".refs { font-size: 0.85em; padding-left: 1.6em; } .refs li { margin-bottom: 3px; }\n"))
    html_ = (f'<h1 class="title">{esc(title)}</h1><div class="authors">{auth}</div><div class="affs">{aff}</div>'
             f'<div class="abstract"><strong>Abstract</strong>{esc(pr.para(4, 7))}</div>'
             f'<div class="body">{"".join(body)}<h2>References</h2><ol class="refs">{refs}</ol></div>')
    return dict(title=title, css=css, body=html_)


# ----------------------------------------------------------------------------- newsletter / brochure

def g_newsletter(r, i):
    st = Style(r)
    pr = Prose(r, r.choice(["marketing", "business", "narrative"]))
    org = company(r)
    c = st.c
    name = r.choice(["The Weekly Digest", "Insider", "Community News", "Monthly Update", "The Bulletin", "Pulse", "Dispatch"])
    issue = f"Issue {r.randint(1, 120)} · {r.choice(MONTHS)} {r.randint(2023, 2025)}"
    arts = []
    for k in range(r.randint(4, 10)):
        img = svg_placeholder(r, st.p, 600, r.choice([240, 300, 340]), r.choice([None, "Photo"])) if r.random() < 0.5 else ""
        arts.append(f'<article class="art{" feature" if k == 0 else ""}">{img}<div class="kicker">{esc(r.choice(["NEWS", "UPDATE", "SPOTLIGHT", "EVENTS", "PEOPLE", "TIPS"]))}</div>'
                    f'<h2>{esc(pr.title(3, 7))}</h2>{prose_paras(pr, r.randint(1, 3), 2, 5)}</article>')
    quote = f'<blockquote class="pull">“{esc(pr.sentence())}”<cite>— {esc(person(r))}</cite></blockquote>'
    arts.insert(r.randint(1, len(arts)), quote)
    events = "".join(f'<li><span class="d">{r.randint(1, 28)} {r.choice(MON3)}</span>{esc(pr.title(2, 4))}</li>' for _ in range(r.randint(3, 6)))
    grid = r.choice(["grid", "columns"])
    css = base_css(st, page_css(st, r, name, none_prob=0.3), (
        f".mast {{ {st.bg_strong()} color: #fff; padding: 22px 26px; border-radius: {st.radius}px; display: flex; justify-content: space-between; align-items: flex-end; }}\n"
        ".mast h1 { color: #fff; margin: 0; font-size: 2.6em; } .mast .issue { font-size: 0.9em; opacity: 0.9; }\n"
        + (".content { display: grid; grid-template-columns: repeat(2, 1fr); gap: 22px; margin-top: 20px; } .feature { grid-column: 1 / -1; }\n"
           if grid == "grid" else f".content {{ column-count: {r.choice([2, 3])}; column-gap: 22px; margin-top: 20px; }} .art {{ break-inside: avoid; margin-bottom: 14px; }}\n")
        + f".art svg {{ width: 100%; height: auto; border-radius: {st.radius}px; display: block; }} .art h2 {{ margin: 6px 0; font-size: 1.25em; }}\n"
        + f".kicker {{ font-size: 0.72em; letter-spacing: 0.14em; color: {c('accent')}; font-weight: 700; margin-top: 8px; }}\n"
        + f".pull {{ font-size: 1.3em; font-style: italic; color: {c('primary')}; border-left: 4px solid {c('accent')}; margin: 0; padding: 8px 16px; break-inside: avoid; }}\n"
        + ".pull cite { display: block; font-size: 0.7em; margin-top: 6px; font-style: normal; }\n"
        + f".events {{ background: {c('soft')}; padding: 16px 20px; border-radius: {st.radius}px; margin-top: 20px; break-inside: avoid; }}\n"
        + f".events ul {{ list-style: none; padding: 0; margin: 0; }} .events li {{ padding: 6px 0; border-bottom: 1px solid {c('border')}; }}\n"
        + f".events .d {{ display: inline-block; width: 64px; font-weight: 700; color: {c('primary')}; }}\n"
        + f".foot {{ margin-top: 24px; font-size: 0.8em; color: {c('muted')}; text-align: center; border-top: 1px solid {c('border')}; padding-top: 10px; }}\n"))
    body = (f'<header class="mast"><div><div class="org">{esc(org)}</div><h1>{esc(name)}</h1></div><div class="issue">{esc(issue)}</div></header>'
            f'<div class="content">{"".join(arts)}</div><aside class="events"><h3>Upcoming</h3><ul>{events}</ul></aside>'
            f'<footer class="foot">{esc(org)} · {esc(", ".join(address(r)))} · You are receiving this because you subscribed.</footer>')
    return dict(title=name, css=css, body=body)


def g_brochure(r, i):
    st = Style(r, serif=False)
    pr = Prose(r, "marketing")
    co = company(r)
    c = st.c
    land = r.random() < 0.55
    pg = (f"@page {{ size: {r.choice(['A4 landscape', 'letter landscape', 'A4 landscape'])}; margin: {r.choice(['0', '10mm', '8mm', '12mm'])}; }}\n" if land
          else page_css(st, r, none_prob=0.3, numbers=0.1))
    panels = []
    for k in range(r.choice([3, 3, 4, 6])):
        feats = "".join(f'<li>{check_icon(st.p["accent"])} {esc(pr.sentence()[:60])}</li>' for _ in range(r.randint(2, 5)))
        img = f'<div class="media">{svg_placeholder(r, st.p, 400, 220)}</div>' if r.random() < 0.5 else ""
        panels.append(f'<div class="panel">{img}<h2>{esc(pr.title(2, 4))}</h2><p>{esc(pr.para(1, 3))}</p><ul class="feats">{feats}</ul></div>')
    hero = (f'<section class="hero"><div class="hero-in">{svg_logo(r, st.p, co, 56)}<h1>{esc(pr.title(3, 6))}</h1><p class="lead">{esc(pr.para(1, 2))}</p>'
            f'<span class="cta">{esc(r.choice(["Book a demo", "Get started today", "Learn more", "Call us now"]))}</span></div></section>')
    pricing = ""
    if r.random() < 0.6:
        tiers = [("Starter", r.randint(9, 29)), ("Pro", r.randint(39, 99)), ("Enterprise", r.randint(149, 499))]
        pricing = '<section class="pricing">' + "".join(
            f'<div class="tier{" pop" if k == 1 else ""}"><h3>{t}</h3><div class="price">${p}<span>/mo</span></div><ul>'
            + "".join(f"<li>{esc(r.choice(SERVICES))}</li>" for _ in range(4)) + "</ul></div>" for k, (t, p) in enumerate(tiers)) + "</section>"
    contact = f'<section class="contact"><strong>{esc(co)}</strong> · {esc(phone(r))} · {esc(email(r, person(r), co))} · {esc(", ".join(address(r)))}</section>'
    css = base_css(st, pg, (
        f".hero {{ {st.bg_strong()} color: #fff; padding: {r.choice(['40px', '48px 40px', '32px'])}; border-radius: {st.radius}px; }}\n"
        ".hero h1 { color: #fff; font-size: 2.4em; margin: 12px 0; } .lead { font-size: 1.15em; opacity: 0.92; max-width: 70%; }\n"
        f".cta {{ display: inline-block; margin-top: 14px; background: #fff; color: {c('primary')}; padding: 10px 22px; border-radius: 999px; font-weight: 700; }}\n"
        f".panels {{ display: grid; grid-template-columns: repeat({3 if land else 2}, 1fr); gap: 20px; margin-top: 22px; }}\n"
        + card_css(st, "panel") + f".panel .media svg {{ width: 100%; height: auto; border-radius: {st.radius}px; display: block; }} .panel h2 {{ font-size: 1.2em; color: {c('primary')}; }}\n"
        + ".feats { list-style: none; padding: 0; } .feats li { margin: 4px 0; }\n"
        + ".pricing { display: flex; gap: 18px; margin-top: 22px; break-inside: avoid; } .tier { flex: 1; border: 1px solid #ddd; border-radius: 12px; padding: 18px; text-align: center; }\n"
        + f".tier.pop {{ border: 2px solid {c('accent')}; transform: scale(1.03); {st.shadow_css(2)} }} .price {{ font-size: 2em; font-weight: 800; color: {c('dark')}; }}\n"
        + ".price span { font-size: 0.4em; font-weight: 400; } .tier ul { list-style: none; padding: 0; text-align: left; }\n"
        + f".contact {{ margin-top: 22px; padding: 14px; text-align: center; background: {c('soft')}; border-radius: {st.radius}px; }}\n"))
    return dict(title=f"{co} brochure", css=css, body=hero + f'<section class="panels">{"".join(panels)}</section>' + pricing + contact)


# ----------------------------------------------------------------------------- certificate

def g_certificate(r, i):
    st = Style(r, serif=True)
    c = st.c
    kind = r.choice(["Certificate of Completion", "Certificate of Achievement", "Certificate of Appreciation", "Award of Excellence",
                     "Certificate of Participation", "Diploma", "Certificate of Attendance"])
    name = person(r)
    org = company(r)
    size = r.choice(["A4 landscape", "letter landscape", "A4 landscape", "A4"])
    margin = r.choice(["0", "10mm", "12mm", "0"])
    frame = r.choice(["double", "ornate", "gradient", "simple"])
    if frame == "double":
        fcss = f".cert {{ border: 10px double {c('primary')}; outline: 2px solid {c('accent')}; outline-offset: -22px; }}\n"
    elif frame == "ornate":
        fcss = f".cert {{ border: 14px solid {c('dark')}; box-shadow: inset 0 0 0 4px #fff, inset 0 0 0 7px {c('accent')}; }}\n"
    elif frame == "gradient":
        fcss = f".cert {{ border: 12px solid transparent; background: linear-gradient(#fff, #fff) padding-box, linear-gradient(135deg, {c('primary')}, {c('accent')}) border-box; }}\n"
    else:
        fcss = f".cert {{ border: 3px solid {c('primary')}; }}\n"
    page_h = 210 if size == "A4 landscape" else 215.9 if size == "letter landscape" else 297
    inner = page_h - (24 if margin == "0" else 2 * int(margin[:-2])) - r.choice([2, 4, 6])
    h = f"{inner:g}mm"
    css = base_css(st, f"@page {{ size: {size}; margin: {margin}; }}\n", (
        "html, body { margin: 0; padding: 0; }\n"
        f".cert {{ box-sizing: border-box; height: {h}; margin: {'12mm' if margin == '0' else '0'}; padding: 40px 60px; text-align: center; position: relative; "
        "display: flex; flex-direction: column; justify-content: center; align-items: center; }\n" + fcss
        + f".kind {{ font-size: 2.6em; color: {c('dark')}; letter-spacing: 0.06em; text-transform: uppercase; margin: 10px 0; }}\n"
        + f".to {{ font-size: 1.1em; color: {c('muted')}; letter-spacing: 0.2em; text-transform: uppercase; }}\n"
        + f".name {{ font-family: {r.choice(SCRIPT_STACKS)}; font-size: 3.2em; color: {c('primary')}; margin: 12px 0; border-bottom: 1px solid {c('border')}; padding: 0 40px 6px; }}\n"
        + ".why { max-width: 70%; font-size: 1.1em; } .sigs { display: flex; gap: 80px; margin-top: 36px; }\n"
        + f".sig {{ min-width: 180px; border-top: 1px solid {c('text')}; padding-top: 6px; font-size: 0.9em; }} .seal {{ position: absolute; {r.choice(['bottom: 40px; right: 60px;', 'bottom: 40px; left: 60px;', 'top: 40px; right: 50px;'])} }}\n"))
    body = (f'<div class="cert">{svg_logo(r, st.p, org, 56)}<div class="kind">{esc(kind)}</div><div class="to">This is proudly presented to</div>'
            f'<div class="name">{esc(name)}</div><p class="why">for {esc(r.choice(["successfully completing", "outstanding performance in", "dedicated contribution to", "participation in"]))} '
            f'<strong>{esc(Prose(r, "business").title(2, 5))}</strong>, awarded on {esc(date(r))}.</p>'
            f'<div class="sigs"><div class="sig">{esc(person(r))}<br>Director</div><div class="sig">{esc(person(r))}<br>{esc(org)}</div></div>'
            f'<div class="seal">{svg_seal(st, r.choice(["AWARD", "CERTIFIED", "SEAL", str(r.randint(2023, 2025))]), r.choice([90, 110, 120]))}</div></div>')
    return dict(title=kind, css=css, body=body)


# ----------------------------------------------------------------------------- menu, tickets

def g_menu(r, i):
    st = Style(r, serif=r.random() < 0.6)
    c = st.c
    rest = r.choice(["La Piazza", "The Copper Kettle", "Saffron House", "Blue Harbor Grill", "Olive & Thyme", "Kumo Izakaya", "Maison Lumière"])
    cur = r.choice(CURRENCIES[:4])
    secs = r.sample(["Starters", "Soups & Salads", "Mains", "From the Grill", "Pasta", "Sides", "Desserts", "Drinks", "Wines by the Glass", "Kids"], r.randint(3, 7))
    blocks = []
    for s in secs:
        items = "".join(f'<div class="item"><div class="row"><span class="nm">{esc(r.choice(DISHES))}</span><span class="dots"></span>'
                        f'<span class="pr">{fmt_money(r.uniform(4, 48), cur)}</span></div>'
                        + (f'<div class="ds">{esc(lorem(r, r.randint(5, 14)))}</div>' if r.random() < 0.7 else "")
                        + (f' <span class="tag">{r.choice(["V", "VG", "GF", "Spicy"])}</span>' if r.random() < 0.2 else "") + "</div>" for _ in range(r.randint(3, 8)))
        blocks.append(f'<section class="msec"><h2>{esc(s)}</h2>{items}</section>')
    cols = r.choice([1, 2, 2])
    css = base_css(st, page_css(st, r, none_prob=0.4, numbers=0.1), (
        f".mhead {{ text-align: center; margin-bottom: 20px; }} .mhead h1 {{ font-size: 2.8em; margin: 0; letter-spacing: 0.08em; color: {c('dark')}; }}\n"
        f".mhead .tag-line {{ color: {c('muted')}; font-style: italic; }} .orn {{ color: {c('accent')}; letter-spacing: 0.5em; }}\n"
        + (f".menu {{ column-count: 2; column-gap: 36px; }} .msec {{ break-inside: avoid; }}\n" if cols == 2 else ".menu { max-width: 600px; margin: 0 auto; }\n")
        + f".msec h2 {{ text-align: center; text-transform: uppercase; letter-spacing: 0.15em; font-size: 1.1em; color: {c('primary')}; border-bottom: 1px solid {c('border')}; padding-bottom: 4px; }}\n"
        + ".item { margin: 8px 0; break-inside: avoid; } .row { display: flex; align-items: baseline; gap: 6px; } .nm { font-weight: 600; }\n"
        + f".dots {{ flex: 1; border-bottom: 1px dotted {c('muted')}; }} .ds {{ font-size: 0.85em; color: {c('muted')}; font-style: italic; }}\n"
        + f".tag {{ font-size: 0.7em; border: 1px solid {c('accent')}; color: {c('accent')}; border-radius: 3px; padding: 0 4px; }}\n"
        + f".mfoot {{ text-align: center; font-size: 0.8em; color: {c('muted')}; margin-top: 20px; }}\n"))
    body = (f'<header class="mhead"><div class="orn">✦ ✦ ✦</div><h1>{esc(rest)}</h1><div class="tag-line">{esc(r.choice(["Seasonal kitchen", "Est. 1987", "Dinner menu", "Lunch & brunch"]))}</div></header>'
            f'<div class="menu">{"".join(blocks)}</div><div class="mfoot">Please inform staff of any allergies. A discretionary 12.5% service charge applies.</div>')
    return dict(title=f"{rest} menu", css=css, body=body)


def g_ticket(r, i):
    st = Style(r, serif=False)
    c = st.c
    kind = r.choice(["boarding", "boarding", "event", "train"])
    n = r.choice([1, 1, 2, 3, 4])
    tickets = []
    for _ in range(n):
        if kind == "boarding":
            (o, on), (d, dn) = r.sample(AIRPORTS, 2)
            main = (f'<div class="route"><div><div class="code">{o}</div><div class="city">{on}</div></div><div class="plane">✈</div>'
                    f'<div><div class="code">{d}</div><div class="city">{dn}</div></div></div>'
                    f'<div class="grid">' + "".join(f'<div><div class="lab">{k}</div><div class="val">{esc(v)}</div></div>' for k, v in [
                        ("Passenger", person(r).upper()), ("Flight", f"{r.choice(['SK', 'OA', 'NS', 'AU', 'ME'])}{r.randint(100, 9999)}"),
                        ("Date", f"{r.randint(1, 28):02d} {r.choice(MON3).upper()}"), ("Boarding", f"{r.randint(5, 22):02d}:{r.choice(['05', '15', '30', '45'])}"),
                        ("Gate", f"{r.choice('ABCDEF')}{r.randint(1, 60)}"), ("Seat", f"{r.randint(1, 45)}{r.choice('ABCDEF')}"),
                        ("Class", r.choice(["Economy", "Business", "Premium"])), ("Zone", str(r.randint(1, 5)))]) + "</div>")
            hdr = esc(r.choice(AIRLINES)) + " · BOARDING PASS"
        elif kind == "train":
            a_, b_ = r.sample([x[1] for x in AIRPORTS], 2)
            main = (f'<div class="route"><div><div class="code">{esc(a_[:3].upper())}</div><div class="city">{esc(a_)}</div></div><div class="plane">→</div>'
                    f'<div><div class="code">{esc(b_[:3].upper())}</div><div class="city">{esc(b_)}</div></div></div><div class="grid">'
                    + "".join(f'<div><div class="lab">{k}</div><div class="val">{esc(v)}</div></div>' for k, v in [
                        ("Passenger", person(r)), ("Train", f"IC {r.randint(100, 999)}"), ("Coach", str(r.randint(1, 14))), ("Seat", str(r.randint(1, 90))),
                        ("Departs", f"{r.randint(5, 22):02d}:{r.randint(0, 59):02d}"), ("Date", iso_date(r))]) + "</div>")
            hdr = "RAIL TICKET · " + r.choice(["Standard", "First class", "Advance single"])
        else:
            ev = r.choice(["Summer Music Festival", "Tech Summit", "City Marathon Expo", "Jazz Night", "Design Conference", "Championship Final"])
            main = (f'<div class="ev">{esc(ev)} {r.randint(2024, 2026)}</div><div class="grid">' + "".join(
                f'<div><div class="lab">{k}</div><div class="val">{esc(v)}</div></div>' for k, v in [
                    ("Venue", company(r).split()[0] + " Arena"), ("Date", date(r, 2025, 2026)), ("Doors", f"{r.randint(16, 20)}:00"),
                    ("Section", r.choice("ABCDEFGH")), ("Row", str(r.randint(1, 40))), ("Seat", str(r.randint(1, 30))),
                    ("Holder", person(r)), ("Price", money(r.uniform(25, 400)))]) + "</div>")
            hdr = "ADMIT ONE"
        code = f"{r.randint(10 ** 9, 10 ** 10 - 1)}"
        stub = f'<div class="stub">{svg_qr(r, 21, 4) if r.random() < 0.6 else svg_barcode(r, 160, 60, code)}<div class="small">{code}</div></div>'
        tickets.append(f'<div class="ticket"><div class="main"><div class="th">{hdr}</div>{main}</div>{stub}</div>')
    css = base_css(st, page_css(st, r, none_prob=0.5, numbers=0.1), (
        f".ticket {{ display: flex; border-radius: {max(st.radius, 8)}px; overflow: hidden; border: 1px solid {c('border')}; margin: 0 0 24px; {st.shadow_css(1)} "
        "break-inside: avoid; page-break-inside: avoid; }\n"
        ".main { flex: 1; padding: 18px 22px; } .th { "
        + st.bg_strong() + " color: #fff; margin: -18px -22px 14px; padding: 10px 22px; font-weight: 700; letter-spacing: 0.1em; font-size: 0.85em; }\n"
        f".stub {{ width: {r.choice(['170px', '190px', '30%'])}; border-left: 2px dashed {c('border')}; padding: 18px; display: flex; flex-direction: column; align-items: center; justify-content: center; background: {c('soft')}; }}\n"
        f".route {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }} .code {{ font-size: 2.6em; font-weight: 800; color: {c('dark')}; line-height: 1; }}\n"
        f".city {{ color: {c('muted')}; font-size: 0.85em; }} .plane {{ font-size: 1.8em; color: {c('accent')}; }} .ev {{ font-size: 1.6em; font-weight: 800; margin-bottom: 12px; color: {c('dark')}; }}\n"
        ".grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px 14px; }\n"
        f".lab {{ font-size: 0.68em; text-transform: uppercase; letter-spacing: 0.1em; color: {c('muted')}; }} .val {{ font-weight: 700; }} .small {{ font-size: 0.75em; margin-top: 6px; font-family: monospace; }}\n"))
    return dict(title=f"{kind.title()} ticket", css=css, body="".join(tickets))


# ----------------------------------------------------------------------------- data tables, dashboards

def g_datatable(r, i):
    st = Style(r, base=r.choice(["9pt", "10pt", "11px", "12px", "8.5pt", "10.5pt"]))
    c = st.c
    kind = r.choice(["transactions", "inventory", "employees", "sales", "log"])
    nrows = r.choice([60, 90, 120, 180, 250, 400, 600])
    rows = []
    if kind == "transactions":
        hdrs = ["Date", "Reference", "Description", "Category", "Debit", "Credit", "Balance"]
        bal = r.uniform(1000, 50000)
        for _ in range(nrows):
            d = r.random() < 0.6
            v = r.uniform(5, 3000)
            bal += -v if d else v
            rows.append([iso_date(r), f"TX{r.randint(100000, 999999)}", esc(r.choice(SERVICES + GOODS)), esc(r.choice(DEPTS)),
                         f"{v:,.2f}" if d else "", "" if d else f"{v:,.2f}", f"{bal:,.2f}"])
        num = (4, 5, 6)
    elif kind == "inventory":
        hdrs = ["SKU", "Item", "Warehouse", "On hand", "Reserved", "Reorder pt", "Unit cost", "Value"]
        for _ in range(nrows):
            oh, uc = r.randint(0, 5000), r.uniform(0.5, 900)
            rows.append([f"SKU-{r.randint(10000, 99999)}", esc(r.choice(GOODS)), r.choice(["AMS-1", "SFO-2", "SIN-1", "FRA-3", "BLR-1"]),
                         f"{oh:,}", f"{r.randint(0, oh):,}", f"{r.randint(10, 500):,}", f"{uc:,.2f}", f"{oh * uc:,.2f}"])
        num = (3, 4, 5, 6, 7)
    elif kind == "employees":
        hdrs = ["ID", "Name", "Department", "Title", "Location", "Start date", "Status"]
        for _ in range(nrows):
            rows.append([str(r.randint(1000, 9999)), esc(person(r)), esc(r.choice(DEPTS)), esc(r.choice(JOBS)), esc(r.choice(address(r)[1:])),
                         iso_date(r, 2010, 2025), badge(r.choice(["ok", "warn", "info"]), r.choice(["Active", "On leave", "Remote"]))])
        num = ()
    elif kind == "sales":
        hdrs = ["Region", "Rep", "Product"] + QUARTERS + ["Total"]
        for _ in range(nrows):
            qs = [r.randint(1000, 90000) for _ in range(4)]
            rows.append([esc(r.choice(REGIONS)), esc(person(r)), esc(r.choice(PRODUCTS))] + [f"{v:,}" for v in qs] + [f"{sum(qs):,}"])
        num = (3, 4, 5, 6, 7)
    else:
        hdrs = ["Timestamp", "Level", "Service", "Message"]
        for _ in range(nrows):
            rows.append([f"{iso_date(r)} {r.randint(0, 23):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}",
                         badge(r.choice(["info", "warn", "bad", "ok"]), r.choice(["INFO", "WARN", "ERROR", "DEBUG"])),
                         r.choice(["api", "auth", "billing", "worker", "db", "cdn"]), esc(lorem(r, r.randint(4, 16)))])
        num = ()
    foot = None
    if kind in ("inventory", "sales") and r.random() < 0.6:
        foot = ["Total"] + [""] * (len(hdrs) - 2) + ["—"]
    title = r.choice([f"{kind.title()} report", f"{kind.title()} — full listing", f"{kind.title()} export {iso_date(r)}"])
    land = len(hdrs) >= 7 and r.random() < 0.4
    pg = page_css(st, r, title, none_prob=0.1, numbers=0.85, sizes=["A4 landscape", "letter landscape"] if land else None)
    css = base_css(st, pg, table_css(st) + badge_css(st) + (
        f".meta {{ display: flex; gap: 24px; color: {c('muted')}; font-size: 0.9em; margin-bottom: 12px; }}\n"
        + ("caption { caption-side: top; text-align: left; font-weight: 600; padding: 6px 0; }\n")
        + (".tbl td:nth-child(4) { max-width: 260px; }\n" if kind == "log" else "")))
    body = (f"<h1>{esc(title)}</h1><div class=\"meta\"><span>Generated {esc(date(r))}</span><span>{nrows} rows</span><span>{esc(company(r))}</span></div>"
            + table_html(hdrs, rows, num_cols=num, foot=foot, caption=r.choice([None, f"Table 1. {kind.title()} data"])))
    if r.random() < 0.25:
        body += f"<h2>Notes</h2><p>{esc(Prose(r).para(2, 4))}</p>"
    return dict(title=title, css=css, body=body)


def g_dashboard(r, i):
    st = Style(r, serif=False, base=r.choice(["10pt", "12px", "13px", "14px", "9.5pt"]))
    c = st.c
    co = company(r)
    title = r.choice(["KPI Dashboard", "Executive Dashboard", "Weekly Metrics", "Marketing Performance", "Ops Scorecard", "SaaS Metrics"])
    land = r.random() < 0.5
    pg = page_css(st, r, title, none_prob=0.2, numbers=0.4, sizes=["A4 landscape", "letter landscape"] if land else None,
                  margins=["10mm", "12mm", "8mm", "0.5in"])
    labels = ["MRR", "ARR", "New signups", "Churn rate", "CAC", "LTV", "Conversion", "Active users", "Tickets", "CSAT", "Uptime", "Avg order"]
    n = r.choice([4, 6, 8])
    kitems = []
    for lab in r.sample(labels, n):
        val = r.choice([f"${r.randint(10, 999)}K", f"{r.randint(1, 99)}.{r.randint(0, 9)}%", f"{r.randint(100, 99999):,}", f"{r.uniform(1, 5):.2f}"])
        spark = svg_spark(r, st.p["series"][r.randint(0, 4)]) if r.random() < 0.6 else None
        kitems.append((lab, val, r.uniform(-15, 30), "", spark))
    kh, kc = kpi_cards(st, kitems, cols=4)
    charts = "".join(f'<div class="panel"><h3>{esc(t)}</h3>{chart(r, st)}</div>' for t in r.sample(
        ["Revenue trend", "Signups by channel", "Regional split", "Pipeline", "Cohort retention", "Costs by department", "Traffic sources"], r.choice([2, 3, 4])))
    rows = [[esc(r.choice(PRODUCTS)), f"{r.randint(100, 9000):,}", f"{r.uniform(-20, 40):+.1f}%", badge(r.choice(["ok", "warn", "bad"]), r.choice(["Healthy", "Watch", "Critical"]))]
            for _ in range(r.randint(5, 12))]
    css = base_css(st, pg, kc + card_css(st, "panel") + table_css(st, font_size="0.9em") + badge_css(st) + (
        f".dash-h {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }} .dash-h h1 {{ margin: 0; font-size: 1.8em; }}\n"
        f".dash-h .meta {{ color: {c('muted')}; }}\n.panels {{ display: grid; grid-template-columns: repeat({3 if land else 2}, 1fr); gap: 16px; margin-top: 16px; }}\n"
        ".panel svg { width: 100%; height: auto; } .panel h3 { margin: 0 0 8px; font-size: 1em; }\n"
        f"body {{ background: {r.choice(['#fff', '#f8fafc', '#f3f4f6'])}; }}\n"))
    body = (f'<div class="dash-h"><div><h1>{esc(title)}</h1><div class="meta">{esc(co)} · {esc(date(r))}</div></div>{svg_logo(r, st.p, co, 40)}</div>'
            f'{kh}<div class="panels">{charts}<div class="panel"><h3>Top products</h3>{table_html(["Product", "Units", "Δ", "Status"], rows, num_cols=(1, 2))}</div></div>')
    return dict(title=title, css=css, body=body)


# ----------------------------------------------------------------------------- letter, spec sheet, minutes, timetable

def g_letter(r, i):
    st = Style(r, serif=r.random() < 0.5, base=r.choice(["11pt", "12pt", "10.5pt", "14px", "15px"]))
    c = st.c
    pr = Prose(r, r.choice(["business", "legal"]))
    co, to_co = company(r), company(r)
    sender, recip = person(r), person(r)
    lh = (f'<header class="lh"><div class="brand">{svg_logo(r, st.p, co, 48)}<div><div class="co">{esc(co)}</div><div class="tag">'
          f'{esc(r.choice(["Excellence since 1998", "Building better futures", "Consulting · Design · Delivery", ""]))}</div></div></div>'
          f'<div class="addr">' + "<br>".join(esc(x) for x in address(r)) + f"<br>{esc(phone(r))}<br>{esc(email(r, sender, co))}</div></header>")
    window = r.random() < 0.3
    rec = f'<div class="recip{" window" if window else ""}">{esc(recip)}<br>{esc(to_co)}<br>' + "<br>".join(esc(x) for x in address(r)) + "</div>"
    subj = r.choice(["Re: Proposal for ", "Subject: ", "Re: ", "Regarding: "]) + pr.title(2, 5)
    paras = prose_paras(pr, r.randint(3, 9), 2, 5)
    if r.random() < 0.3:
        paras += "<ul>" + "".join(f"<li>{esc(pr.sentence())}</li>" for _ in range(r.randint(2, 5))) + "</ul>" + prose_paras(pr, 1)
    close = (f'<div class="close"><p>{esc(r.choice(["Sincerely,", "Kind regards,", "Best regards,", "Yours faithfully,"]))}</p><div class="sig">{esc(sender)}</div>'
             f'<div>{esc(r.choice(JOBS))}<br>{esc(co)}</div></div>')
    enc = '<p class="enc">Enclosures: ' + ", ".join(r.sample(["Proposal", "Price schedule", "Terms and conditions", "Brochure", "Invoice"], 2)) + "</p>" if r.random() < 0.4 else ""
    css = base_css(st, page_css(st, r, none_prob=0.45, numbers=0.3, margins=["20mm", "25mm 20mm", "1in", "2.5cm 2cm", "18mm"]), (
        f".lh {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid {c('primary')}; padding-bottom: 12px; margin-bottom: 28px; }}\n"
        f".brand {{ display: flex; gap: 12px; align-items: center; }} .co {{ font-size: 1.4em; font-weight: 700; color: {c('primary')}; }} .tag {{ color: {c('muted')}; font-size: 0.85em; }}\n"
        f".addr {{ text-align: right; font-size: 0.82em; color: {c('muted')}; }}\n"
        + (".recip.window { position: absolute; top: 45mm; left: 0; width: 85mm; height: 40mm; } body { position: relative; } .date { margin-top: 70mm; }\n" if window else ".recip { margin-bottom: 20px; }\n")
        + ".date { text-align: right; margin-bottom: 20px; } .subj { font-weight: 700; margin-bottom: 16px; }\n"
        + f".close {{ margin-top: 24px; break-inside: avoid; }} .sig {{ font-family: {r.choice(SCRIPT_STACKS)}; font-size: 1.8em; color: {c('dark')}; margin: 8px 0 2px; }}\n"
        + f".enc {{ font-size: 0.85em; color: {c('muted')}; margin-top: 18px; }} p {{ text-align: {r.choice(['left', 'justify'])}; }}\n"))
    body = lh + rec + f'<div class="date">{esc(date(r))}</div><div class="subj">{esc(subj)}</div><p>Dear {esc(recip.split()[0])},</p>' + paras + close + enc
    return dict(title=subj, css=css, body=body)


def g_specsheet(r, i):
    st = Style(r, serif=False)
    c = st.c
    pr = Prose(r, "marketing")
    prod = r.choice(PRODUCTS)
    feats = "".join(f"<li>{check_icon(st.p['primary'])} {esc(pr.sentence()[:70])}</li>" for _ in range(r.randint(4, 8)))
    spec_keys = ["Dimensions", "Weight", "Power supply", "Operating temp.", "Connectivity", "Ingress protection", "Material", "Certifications",
                 "Warranty", "Display", "Battery", "Interfaces", "Max load", "Accuracy", "Storage", "Mounting"]
    specs = [[esc(k), esc(v)] for k, v in zip(r.sample(spec_keys, r.randint(8, 16)), [
        f"{r.randint(50, 400)} × {r.randint(50, 400)} × {r.randint(10, 120)} mm", f"{r.uniform(0.2, 12):.1f} kg", f"{r.choice([5, 12, 24, 48])} V DC",
        f"-{r.randint(10, 40)} °C to +{r.randint(50, 85)} °C", "Wi-Fi 6, Bluetooth 5.3, Ethernet", f"IP{r.choice([54, 65, 67, 68])}", "Anodized aluminium",
        "CE, FCC, RoHS, UL", f"{r.randint(1, 5)} years", f"{r.choice([2.4, 3.5, 5, 7])}\" TFT", f"{r.randint(1000, 9000)} mAh", "USB-C, RS-485, CAN",
        f"{r.randint(5, 500)} kg", f"±{r.uniform(0.1, 2):.1f}%", f"{r.choice([16, 32, 64, 128])} GB", "DIN rail / wall"] * 2)]
    order = [[f"{prod.split()[0][:3].upper()}-{r.randint(100, 999)}{s}", esc(v), money(r.uniform(99, 4999))] for s, v in
             zip("ABCD", ["Standard", "Pro", "Extended range", "Industrial"])][:r.randint(2, 4)]
    dims = (f'<svg width="260" height="160" viewBox="0 0 260 160"><rect x="40" y="30" width="180" height="90" rx="8" fill="{st.p["soft"]}" stroke="{st.p["dark"]}" stroke-width="2"/>'
            f'<line x1="40" y1="140" x2="220" y2="140" stroke="{st.p["muted"]}"/><text x="130" y="155" text-anchor="middle" font-size="11">{r.randint(80, 300)} mm</text>'
            f'<line x1="235" y1="30" x2="235" y2="120" stroke="{st.p["muted"]}"/><text x="245" y="80" font-size="11" transform="rotate(90 245 80)">{r.randint(40, 200)} mm</text></svg>')
    css = base_css(st, page_css(st, r, prod, none_prob=0.3), table_css(st) + (
        f".hero {{ display: grid; grid-template-columns: 1.1fr 1fr; gap: 24px; align-items: center; }} .hero .media svg {{ width: 100%; height: auto; border-radius: {st.radius}px; }}\n"
        f".model {{ color: {c('accent')}; font-weight: 700; letter-spacing: 0.1em; font-size: 0.85em; }}\n"
        ".feats { list-style: none; padding: 0; } .feats li { margin: 6px 0; }\n"
        ".cols { display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px; margin-top: 20px; }\n"
        f".box {{ border: 1px solid {c('border')}; border-radius: {st.radius}px; padding: 14px; break-inside: avoid; }}\n"
        f".legal {{ font-size: 0.75em; color: {c('muted')}; margin-top: 20px; }}\n"))
    body = (f'<section class="hero"><div><div class="model">DATASHEET · REV {r.randint(1, 9)}.{r.randint(0, 9)}</div><h1>{esc(prod)}</h1><p>{esc(pr.para(2, 3))}</p>'
            f'<ul class="feats">{feats}</ul></div><div class="media">{svg_placeholder(r, st.p, 500, 360, prod.split()[0])}</div></section>'
            f'<div class="cols"><div><h2>Technical specifications</h2>{table_html(["Parameter", "Value"], specs)}</div>'
            f'<div><h2>Dimensions</h2><div class="box">{dims}</div><h2>Ordering information</h2>{table_html(["Part no.", "Variant", "Price"], order, num_cols=(2,))}</div></div>'
            f'<p class="legal">Specifications subject to change without notice. © {r.randint(2023, 2025)} {esc(company(r))}. All rights reserved.</p>')
    return dict(title=f"{prod} datasheet", css=css, body=body)


def g_minutes(r, i):
    st = Style(r)
    c = st.c
    pr = Prose(r, "business")
    team = [person(r) for _ in range(r.randint(4, 12))]
    title = r.choice(["Board Meeting Minutes", "Project Steering Committee", "Weekly Team Sync", "Quarterly Planning Meeting", "Product Review"])
    meta = [["Date", esc(date(r))], ["Time", f"{r.randint(8, 16)}:00 – {r.randint(9, 18)}:30"], ["Location", esc(r.choice(["Room 4B", "Zoom", "HQ Boardroom", "Teams"]))],
            ["Chair", esc(team[0])], ["Minutes by", esc(team[1])], ["Attendees", esc(", ".join(team))]]
    items = []
    for k in range(r.randint(3, 9)):
        items.append(f'<section class="ag"><h3>{k + 1}. {esc(pr.title(2, 5))}</h3><p>{esc(pr.para(2, 5))}</p>'
                     + (f'<p class="dec"><strong>Decision:</strong> {esc(pr.sentence())}</p>' if r.random() < 0.5 else "") + "</section>")
    acts = [[str(k + 1), esc(pr.sentence()[:80]), esc(r.choice(team)), esc(iso_date(r)), badge(r.choice(["ok", "warn", "info"]), r.choice(["Open", "In progress", "Done"]))]
            for k in range(r.randint(3, 12))]
    css = base_css(st, page_css(st, r, title), table_css(st) + badge_css(st) + (
        f".meta {{ border-collapse: collapse; margin-bottom: 18px; width: 100%; }} .meta th {{ text-align: left; width: 120px; color: {c('muted')}; font-weight: 600; padding: 3px 8px 3px 0; vertical-align: top; }}\n"
        f".meta td {{ padding: 3px 0; }} .ag {{ break-inside: avoid; }} .dec {{ background: {c('soft')}; padding: 8px 12px; border-radius: {st.radius}px; }}\n"))
    body = (f"<h1>{esc(title)}</h1><table class=\"meta\">" + "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in meta) + "</table>"
            f"<h2>Agenda &amp; discussion</h2>{''.join(items)}<h2>Action items</h2>{table_html(['#', 'Action', 'Owner', 'Due', 'Status'], acts)}"
            f"<p>Next meeting: {esc(date(r))}. Meeting adjourned at {r.randint(10, 18)}:{r.choice(['00', '15', '30', '45'])}.</p>")
    return dict(title=title, css=css, body=body)


def g_timetable(r, i):
    st = Style(r, serif=False, base=r.choice(["9pt", "10pt", "11px", "12px"]))
    c = st.c
    kind = r.choice(["school", "conference", "transit"])
    if kind == "transit":
        stops = r.sample([x[1] for x in AIRPORTS] + ["Central", "Riverside", "Old Town", "Airport", "University", "Harbour", "Market", "Park"], r.randint(6, 14))
        ntrips = r.randint(8, 16)
        rows = []
        for s_i, s in enumerate(stops):
            rows.append([f"<strong>{esc(s)}</strong>"] + [f"{(6 + t) % 24:02d}:{(s_i * 7 + t * 13) % 60:02d}" for t in range(ntrips)])
        tbl = table_html(["Stop"] + [f"{r.choice(['R', 'S', 'X'])}{100 + t}" for t in range(ntrips)], rows, num_cols=tuple(range(1, ntrips + 1)))
        title = f"Line {r.randint(1, 99)} timetable — weekdays"
    else:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"] if kind == "school" else ["Day 1", "Day 2", "Day 3"]
        slots = [f"{h:02d}:00" for h in range(8, 8 + r.randint(6, 10))]
        subj = ["Mathematics", "Physics", "Chemistry", "History", "English", "Art", "Biology", "Computer Science", "PE", "Music", "Geography"] if kind == "school" else \
            ["Keynote", "Workshop", "Panel", "Lunch", "Networking", "Lightning talks", "Breakout A", "Breakout B", "Closing remarks"]
        cols_ = st.p["series"]
        rows = []
        for s in slots:
            row = [f"<strong>{s}</strong>"]
            for _ in days:
                sname = r.choice(subj)
                col = cols_[subj.index(sname) % len(cols_)]
                row.append(f'<div class="slot" style="border-left-color:{col}"><div class="sn">{esc(sname)}</div><div class="rm">{esc(r.choice(["Room 101", "Lab 2", "Hall A", "Room 12", "Main stage"]))}</div></div>')
            rows.append(row)
        tbl = table_html(["Time"] + days, rows)
        title = "Class timetable" if kind == "school" else f"{company(r)} Conference — Programme"
    land = r.random() < 0.6
    css = base_css(st, page_css(st, r, title, none_prob=0.3, sizes=["A4 landscape", "letter landscape"] if land else None),
                   table_css(st, variant=r.choice(["bordered", "striped", "header-dark"])) + (
        f".slot {{ border-left: 4px solid {c('primary')}; padding: 2px 6px; background: {c('soft')}; border-radius: 3px; }} .sn {{ font-weight: 600; }} .rm {{ font-size: 0.8em; color: {c('muted')}; }}\n"
        ".tbl td, .tbl th { text-align: center; } .tbl td:first-child { text-align: left; white-space: nowrap; }\n"))
    return dict(title=title, css=css, body=f"<h1>{esc(title)}</h1><p>Valid from {esc(date(r))}. Subject to change.</p>{tbl}")


# ----------------------------------------------------------------------------- long-form

def g_longform(r, i):
    st = Style(r, serif=r.random() < 0.55, base=r.choice(["10.5pt", "11pt", "12pt", "11pt", "15px"]))
    c = st.c
    dom = r.choice(["business", "narrative", "academic", "legal"])
    pr = Prose(r, dom)
    title = r.choice(["Employee Handbook", "Operations Manual", "The Northern Ridge", "Technical Reference Guide", "Policy Compendium",
                      "Field Notes", "Annual Review: Detailed Findings", "Product Documentation"])
    target_pages = r.randint(20, 60)
    total_paras = target_pages * r.choice([5, 6, 6, 7])
    nchap = r.randint(6, 16)
    per = max(4, total_paras // nchap)
    chaps, toc = [], []
    for k in range(nchap):
        ct = pr.title(2, 5)
        toc.append(f"<li>Chapter {k + 1}: {esc(ct)}</li>")
        parts = [f'<section class="chap"><div class="cn">Chapter {k + 1}</div><h1>{esc(ct)}</h1>']
        left = per
        sec = 1
        while left > 0:
            if r.random() < 0.3:
                parts.append(f"<h2>{k + 1}.{sec} {esc(pr.title(2, 5))}</h2>")
                sec += 1
            roll = r.random()
            if roll < 0.04:
                parts.append(f'<blockquote>{esc(pr.para(1, 3))}</blockquote>')
            elif roll < 0.07:
                parts.append("<ul>" + "".join(f"<li>{esc(pr.sentence())}</li>" for _ in range(r.randint(3, 7))) + "</ul>")
            elif roll < 0.09 and dom != "narrative":
                rows = [[esc(pr.title(1, 3)), esc(pr.sentence()[:60]), str(r.randint(1, 999))] for _ in range(r.randint(4, 14))]
                parts.append(table_html(["Item", "Description", "Value"], rows, num_cols=(2,)))
            elif roll < 0.1 and dom != "narrative":
                parts.append(f'<pre class="code">{esc(chr(10).join(lorem(r, r.randint(3, 8)) for _ in range(r.randint(3, 9))))}</pre>')
            elif roll < 0.115:
                parts.append(figure(r, st, f"Figure {k + 1}.{sec}", chart(r, st)))
            else:
                parts.append(f"<p>{esc(pr.para(3, 7))}</p>")
            left -= 1
        parts.append("</section>")
        chaps.append("".join(parts))
    cover = (f'<section class="cover"><h1 class="t">{esc(title)}</h1><div class="by">{esc(person(r))}</div><div class="ed">{esc(company(r))} · {r.randint(2020, 2025)}</div></section>'
             f'<nav class="toc"><h2>Contents</h2><ol>{"".join(toc)}</ol></nav>')
    css = base_css(st, page_css(st, r, title, none_prob=0.05, numbers=0.9), table_css(st) + fig_css(st) + (
        f".cover {{ height: 230mm; display: flex; flex-direction: column; justify-content: center; text-align: center; break-after: page; }} .cover .t {{ font-size: 3em; color: {c('primary')}; }}\n"
        ".toc { break-after: page; } .toc li { margin: 4px 0; }\n"
        f".chap {{ break-before: page; page-break-before: always; }} .cn {{ text-transform: uppercase; letter-spacing: 0.2em; color: {c('accent')}; font-size: 0.85em; }}\n"
        f"p {{ text-align: {r.choice(['justify', 'left'])}; margin: 0 0 {r.choice(['0.6em', '0.8em', '0'])}; {r.choice(['', 'text-indent: 1.5em;'])} orphans: 2; widows: 2; }}\n"
        f"blockquote {{ margin: 12px 24px; padding-left: 12px; border-left: 3px solid {c('border')}; font-style: italic; }}\n"
        f".code {{ font-family: {st.mono}; font-size: 0.85em; background: #f6f8fa; padding: 10px; border-radius: 4px; white-space: pre-wrap; break-inside: avoid; }}\n"
        "h2 { break-after: avoid; }\n"))
    return dict(title=title, css=css, body=cover + "".join(chaps), meta={"target_pages": target_pages})


# ----------------------------------------------------------------------------- multilingual

def g_i18n(r, i):
    code = ["ar", "zh", "ja", "ko", "hi", "ru", "mixed"][i % 7]
    if code == "mixed":
        return g_mixed(r, i)
    Ld = LANGS[code]
    L = Ld["L"]
    st = Style(r, serif=False)
    st.font = r.choice(Ld["fonts"])
    st.head_font = st.font
    c = st.c
    kind = r.choice(["letter", "invoice", "report", "menu", "notice"])
    rtl = Ld["dir"] == "rtl"
    S = Ld["s"]

    def paras(n):
        return "".join("<p>" + esc(" ".join(r.choice(S) for _ in range(r.randint(2, 5)))) + "</p>" for _ in range(n))
    cur = r.choice(CURRENCIES)
    if kind == "invoice":
        items = [(r.choice(Ld["items"]), r.randint(1, 9), round(r.uniform(10, 900), 2)) for _ in range(r.randint(3, 14))]
        sub = sum(q * p for _, q, p in items)
        tax = sub * 0.15
        rows = [[esc(d), str(q), fmt_money(p, cur), fmt_money(q * p, cur)] for d, q, p in items]
        hdr, hcss = header_block(st, L["invoice"], esc(company(r)), svg_logo(r, st.p, "AB", 44), f"{esc(L['no'])}: {r.randint(1000, 9999)}<br>{esc(L['date'])}: {esc(iso_date(r))}")
        body = (hdr + f"<p><strong>{esc(L['customer'])}:</strong> {esc(person(r))}</p>"
                + table_html([L["desc"], L["qty"], L["price"], L["amount"]], rows, num_cols=(1, 2, 3),
                             foot=[L["total"], "", "", fmt_money(sub + tax, cur)])
                + f'<p class="sum">{esc(L["subtotal"])}: {fmt_money(sub, cur)} · {esc(L["tax"])}: {fmt_money(tax, cur)}</p><p class="thanks">{esc(L["thanks"])}</p>')
        css_x = hcss + table_css(st)
        title = L["invoice"]
    elif kind == "menu":
        blocks = "".join(f'<section class="msec"><h2>{esc(sec)}</h2>' + "".join(
            f'<div class="row"><span>{esc(d)}</span><span class="dots"></span><span>{fmt_money(r.uniform(3, 40), cur)}</span></div>' for d in dishes) + "</section>"
            for sec, dishes in Ld["menu"])
        title = Ld["titles"][4]
        body = f'<h1 class="mt">{esc(title)}</h1><div class="menu">{blocks}</div>'
        css_x = (f".mt {{ text-align: center; color: {c('primary')}; }} .menu {{ column-count: {r.choice([1, 2])}; column-gap: 32px; }} .msec {{ break-inside: avoid; }}\n"
                 f".row {{ display: flex; gap: 6px; align-items: baseline; margin: 6px 0; }} .dots {{ flex: 1; border-bottom: 1px dotted {c('muted')}; }}\n"
                 f".msec h2 {{ border-bottom: 2px solid {c('accent')}; padding-bottom: 4px; }}\n")
    elif kind == "report":
        title = Ld["titles"][0]
        secs = "".join(f"<h2>{k + 1}. {esc(r.choice(Ld['titles']))}</h2>{paras(r.randint(2, 5))}"
                       + (figure(r, st, Ld["titles"][2], chart(r, st)) if r.random() < 0.4 else "") for k in range(r.randint(3, 10)))
        hdr, hcss = header_block(st, title, esc(company(r)), svg_logo(r, st.p, "XY", 44), esc(iso_date(r)))
        body = hdr + secs
        css_x = hcss + fig_css(st) + "h2 { break-after: avoid; }\n"
    elif kind == "notice":
        title = Ld["titles"][3]
        cb, cc = callout(st, Ld["titles"][2], paras(1))
        body = f"<h1>{esc(title)}</h1>{paras(r.randint(2, 4))}{cb}{paras(r.randint(1, 3))}"
        css_x = cc
    else:
        title = Ld["titles"][1]
        body = (f'<div class="lh"><strong>{esc(company(r))}</strong><span>{esc(iso_date(r))}</span></div><p>{esc(L["dear"])}</p>{paras(r.randint(3, 7))}'
                f'<p class="close">{esc(L["regards"])}<br><strong>{esc(person(r))}</strong></p>')
        css_x = f".lh {{ display: flex; justify-content: space-between; border-bottom: 2px solid {c('primary')}; padding-bottom: 8px; margin-bottom: 24px; }} .close {{ margin-top: 24px; }}\n"
    pg = page_css(st, r, none_prob=0.4, numbers=0.5)
    css = base_css(st, pg, css_x + (f"body {{ direction: rtl; }} .num {{ text-align: left !important; }}\n" if rtl and r.random() < 0.5 else "")
                   + (".tbl th, .tbl td { text-align: start; }\n" if rtl else "")
                   + f"p {{ line-height: {r.choice(['1.7', '1.8', '1.6', '1.9'])}; }} .thanks {{ text-align: center; color: {c('primary')}; }}\n")
    return dict(title=title, css=css, body=body, lang=Ld["lang"], dir=Ld["dir"])


def g_mixed(r, i):
    st = Style(r, serif=False)
    c = st.c
    pr = Prose(r, "business")
    codes = r.sample(["ar", "zh", "ja", "ko", "hi", "ru"], r.randint(2, 5))
    title = r.choice(["Global Customer Notice", "Multilingual Product Guide", "International Office Directory", "Translation Glossary"])
    blocks = [f"<h1>{esc(title)}</h1><p>{esc(pr.para(2, 4))}</p>"]
    for cd in codes:
        Ld = LANGS[cd]
        d = f' dir="{Ld["dir"]}"' if Ld["dir"] else ""
        blocks.append(f'<section class="lang" lang="{Ld["lang"]}"{d} style="font-family: {Ld["font"]}"><h2>{esc(Ld["titles"][r.randint(0, 3)])}</h2>'
                      + "".join(f"<p>{esc(' '.join(r.sample(Ld['s'], min(3, len(Ld['s'])))))}</p>" for _ in range(r.randint(1, 3))) + "</section>")
    keys = ["invoice", "date", "total", "customer", "thanks"]
    rows = [[esc(k.title())] + [f'<span lang="{LANGS[cd]["lang"]}"{" dir=" + chr(34) + "rtl" + chr(34) if LANGS[cd]["dir"] else ""}>{esc(LANGS[cd]["L"][k])}</span>' for cd in codes] for k in keys]
    blocks.append("<h2>Glossary</h2>" + table_html(["English"] + [LANGS[cd]["lang"] for cd in codes], rows))
    inline = " ".join(f'<span lang="{LANGS[cd]["lang"]}">{esc(LANGS[cd]["L"]["thanks"])}</span>' for cd in codes)
    blocks.append(f"<p>{esc(pr.sentence())} {inline} — {esc(pr.sentence())}</p>")
    css = base_css(st, page_css(st, r, title, none_prob=0.3), table_css(st) + (
        f".lang {{ border-{r.choice(['left', 'top'])}: 3px solid {c('accent')}; padding: 8px 14px; margin: 14px 0; background: {c('soft')}; border-radius: {st.radius}px; break-inside: avoid; }}\n"
        ".lang[dir=rtl] { border-left: none; border-right: 3px solid; text-align: right; }\n"))
    return dict(title=title, css=css, body="".join(blocks))


CATEGORIES = [
    ("invoice", g_invoice, 26), ("receipt", g_receipt, 14), ("quote", g_quote, 12), ("report", g_report, 26), ("resume", g_resume, 18),
    ("contract", g_contract, 16), ("paper", g_paper, 16), ("newsletter", g_newsletter, 12), ("brochure", g_brochure, 10),
    ("certificate", g_certificate, 12), ("menu", g_menu, 10), ("ticket", g_ticket, 12), ("datatable", g_datatable, 20),
    ("dashboard", g_dashboard, 14), ("letter", g_letter, 16), ("i18n", g_i18n, 28), ("specsheet", g_specsheet, 10),
    ("minutes", g_minutes, 10), ("timetable", g_timetable, 8), ("longform", g_longform, 10),
]


def generate(out_dir, scale=1.0, only=None):
    os.makedirs(out_dir, exist_ok=True)
    entries = []
    for cat, fn, n in CATEGORIES:
        if only and cat not in only:
            continue
        for k in range(max(1, round(n * scale))):
            r = random.Random(f"{GEN_VERSION}:{cat}:{k}")
            d = fn(r, k)
            doc_id = f"gen_{cat}_{k:03d}"
            html = html_doc(d["title"], d["css"], d["body"], lang=d.get("lang", "en"), dirn=d.get("dir"))
            path = os.path.join(out_dir, doc_id + ".html")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(html)
            e = {"id": doc_id, "category": cat, "source": "generated", "license": "generated (CC0)", "lang": d.get("lang", "en"),
                 "file": os.path.basename(path), "bytes": len(html.encode("utf-8"))}
            e.update(d.get("meta", {}))
            entries.append(e)
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    ents = generate(a.out, a.scale, set(x for x in a.only.split(",") if x))
    with open(os.path.join(a.out, "generated.json"), "w", encoding="utf-8") as f:
        json.dump(ents, f, indent=1, ensure_ascii=False)
    from collections import Counter
    print(json.dumps({"total": len(ents), "by_category": dict(Counter(e["category"] for e in ents))}))


if __name__ == "__main__":
    main()

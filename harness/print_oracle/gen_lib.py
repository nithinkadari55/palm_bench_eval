import html as _html
import math

PALETTES = [
    {"name": "indigo", "primary": "#4f46e5", "accent": "#06b6d4", "text": "#1f2937", "muted": "#6b7280", "border": "#e5e7eb", "soft": "#eef2ff", "dark": "#312e81",
     "series": ["#4f46e5", "#06b6d4", "#f59e0b", "#10b981", "#ef4444"]},
    {"name": "blue", "primary": "#2563eb", "accent": "#f97316", "text": "#111827", "muted": "#6b7280", "border": "#d1d5db", "soft": "#eff6ff", "dark": "#1e3a8a",
     "series": ["#2563eb", "#f97316", "#22c55e", "#a855f7", "#eab308"]},
    {"name": "emerald", "primary": "#059669", "accent": "#0ea5e9", "text": "#064e3b", "muted": "#4b5563", "border": "#d1fae5", "soft": "#ecfdf5", "dark": "#065f46",
     "series": ["#059669", "#0ea5e9", "#f59e0b", "#6366f1", "#e11d48"]},
    {"name": "slate", "primary": "#334155", "accent": "#0284c7", "text": "#0f172a", "muted": "#64748b", "border": "#cbd5e1", "soft": "#f1f5f9", "dark": "#0f172a",
     "series": ["#334155", "#0284c7", "#94a3b8", "#f43f5e", "#14b8a6"]},
    {"name": "rose", "primary": "#e11d48", "accent": "#7c3aed", "text": "#1f2937", "muted": "#6b7280", "border": "#fecdd3", "soft": "#fff1f2", "dark": "#881337",
     "series": ["#e11d48", "#7c3aed", "#f59e0b", "#0891b2", "#16a34a"]},
    {"name": "amber", "primary": "#d97706", "accent": "#1d4ed8", "text": "#292524", "muted": "#78716c", "border": "#e7e5e4", "soft": "#fffbeb", "dark": "#78350f",
     "series": ["#d97706", "#1d4ed8", "#65a30d", "#db2777", "#0d9488"]},
    {"name": "teal", "primary": "#0d9488", "accent": "#f43f5e", "text": "#134e4a", "muted": "#5f6b6a", "border": "#ccfbf1", "soft": "#f0fdfa", "dark": "#115e59",
     "series": ["#0d9488", "#f43f5e", "#6366f1", "#eab308", "#64748b"]},
    {"name": "violet", "primary": "#7c3aed", "accent": "#ec4899", "text": "#1e1b4b", "muted": "#6b7280", "border": "#ddd6fe", "soft": "#f5f3ff", "dark": "#4c1d95",
     "series": ["#7c3aed", "#ec4899", "#14b8a6", "#f97316", "#3b82f6"]},
    {"name": "navy-gold", "primary": "#1e3a5f", "accent": "#c9a227", "text": "#1a1a1a", "muted": "#666666", "border": "#d8d2c4", "soft": "#f8f5ee", "dark": "#0f2236",
     "series": ["#1e3a5f", "#c9a227", "#7a8b99", "#a23b2a", "#3e7c59"]},
    {"name": "mono", "primary": "#111111", "accent": "#555555", "text": "#111111", "muted": "#777777", "border": "#dddddd", "soft": "#f6f6f6", "dark": "#000000",
     "series": ["#111111", "#555555", "#888888", "#aaaaaa", "#cccccc"]},
    {"name": "forest", "primary": "#2f5d3a", "accent": "#b5651d", "text": "#1c2a1f", "muted": "#5c6b5f", "border": "#d5e0d7", "soft": "#f3f7f3", "dark": "#1b3a24",
     "series": ["#2f5d3a", "#b5651d", "#6b8f71", "#d4a373", "#3d5a80"]},
    {"name": "crimson", "primary": "#9b1c31", "accent": "#2b6cb0", "text": "#2d2d2d", "muted": "#707070", "border": "#e2d4d6", "soft": "#fbf4f5", "dark": "#5c0f1c",
     "series": ["#9b1c31", "#2b6cb0", "#d69e2e", "#38a169", "#805ad5"]},
    {"name": "sky", "primary": "#0369a1", "accent": "#facc15", "text": "#0c4a6e", "muted": "#64748b", "border": "#bae6fd", "soft": "#f0f9ff", "dark": "#0c4a6e",
     "series": ["#0369a1", "#facc15", "#f472b6", "#34d399", "#a78bfa"]},
    {"name": "coral", "primary": "#ea580c", "accent": "#0f766e", "text": "#27272a", "muted": "#71717a", "border": "#fed7aa", "soft": "#fff7ed", "dark": "#7c2d12",
     "series": ["#ea580c", "#0f766e", "#6366f1", "#84cc16", "#e11d48"]},
]

FONT_STACKS = [
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    "'Helvetica Neue', Helvetica, Arial, sans-serif",
    "Arial, sans-serif",
    "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
    "Georgia, 'Times New Roman', serif",
    "'Times New Roman', Times, serif",
    "'Roboto', 'Open Sans', 'Helvetica Neue', sans-serif",
    "'DejaVu Sans', sans-serif",
    "'Liberation Sans', Arial, sans-serif",
    "'Liberation Serif', 'Times New Roman', serif",
    "'Noto Sans', sans-serif",
    "'Noto Serif', Georgia, serif",
    "system-ui, sans-serif",
    "'Merriweather', Georgia, serif",
    "'Lato', 'Helvetica Neue', Arial, sans-serif",
    "Verdana, Geneva, sans-serif",
    "'Source Sans Pro', 'Segoe UI', sans-serif",
    "'Playfair Display', Georgia, serif",
]
SERIF_STACKS = [s for s in FONT_STACKS if s.endswith("serif") and "sans-serif" not in s]
MONO_STACKS = [
    "'Courier New', Courier, monospace",
    "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
    "'DejaVu Sans Mono', monospace",
    "monospace",
]

FIRST = ["James", "Olivia", "Liam", "Emma", "Noah", "Ava", "Sophia", "Mason", "Isabella", "Lucas", "Mia", "Ethan", "Amelia", "Aiden",
         "Harper", "Elijah", "Evelyn", "Benjamin", "Abigail", "Daniel", "Priya", "Arjun", "Mei", "Hiroshi", "Fatima", "Omar", "Elena",
         "Mateo", "Chloe", "Samuel", "Grace", "Leo", "Zoe", "Nora", "Ravi", "Aisha", "Carlos", "Ingrid", "Tomasz", "Yuki"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez",
        "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Patel", "Nguyen", "Kim", "Chen", "Okafor",
        "Schmidt", "Rossi", "Dubois", "Kowalski", "Tanaka", "Haddad", "Novak", "Silva", "Andersen", "Fischer", "Murphy", "Khan"]
CO_A = ["Northwind", "Bluepeak", "Acme", "Summit", "Brightline", "Ironwood", "Silverleaf", "Crescent", "Evergreen", "Horizon", "Nimbus",
        "Quantum", "Redwood", "Starlight", "Vertex", "Harbor", "Aurora", "Pinecrest", "Lumen", "Cobalt", "Granite", "Meridian"]
CO_B = ["Labs", "Systems", "Group", "Partners", "Logistics", "Analytics", "Studio", "Holdings", "Consulting", "Technologies",
        "Solutions", "Industries", "Digital", "Ventures", "Health", "Foods", "Energy", "Media", "Works", "Capital"]
STREETS = ["Market Street", "Maple Avenue", "Oak Lane", "Harbor Road", "King Street", "Elm Drive", "Park Avenue", "Riverside Way",
           "Station Road", "Mill Lane", "High Street", "Cedar Court", "Sunset Boulevard", "Bridge Street", "Church Road"]
CITIES = [("San Francisco", "CA 94103", "USA"), ("Austin", "TX 78701", "USA"), ("New York", "NY 10001", "USA"),
          ("London", "EC1A 1BB", "United Kingdom"), ("Manchester", "M1 1AE", "United Kingdom"), ("Berlin", "10115", "Germany"),
          ("Munich", "80331", "Germany"), ("Paris", "75002", "France"), ("Toronto", "ON M5V 2T6", "Canada"),
          ("Sydney", "NSW 2000", "Australia"), ("Dublin", "D02 X285", "Ireland"), ("Amsterdam", "1012 AB", "Netherlands"),
          ("Bengaluru", "560001", "India"), ("Singapore", "018956", "Singapore"), ("Madrid", "28013", "Spain")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
CURRENCIES = [("$", "USD"), ("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("₹", "INR"), ("¥", "JPY"), ("CA$", "CAD"), ("A$", "AUD")]

SERVICES = ["Website redesign", "Brand identity package", "Cloud hosting (monthly)", "SEO audit", "Mobile app development",
            "UX research sprint", "Data migration", "Security assessment", "Content writing (10 articles)", "Logo design",
            "API integration", "Technical support retainer", "Photography session", "Social media management", "Training workshop",
            "Database optimization", "Annual software license", "Consulting hours", "Hardware installation", "Copy editing",
            "Video production", "Market research report", "Email campaign setup", "Network maintenance", "Custom dashboard build"]
GOODS = ["Ergonomic office chair", "27\" 4K monitor", "Wireless keyboard", "USB-C docking station", "Standing desk frame",
         "Noise-cancelling headphones", "Laptop stand (aluminium)", "Webcam 1080p", "LED desk lamp", "Cable management kit",
         "Printer toner (black)", "A4 copy paper, 5 reams", "Whiteboard 120x90 cm", "Coffee beans 1 kg", "Water bottles (24 pack)",
         "Portable SSD 1 TB", "Smartphone case", "HDMI cable 2 m", "Desk organizer", "Notebook set"]

LOREM = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua "
         "enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo consequat duis aute irure in "
         "reprehenderit voluptate velit esse cillum fugiat nulla pariatur excepteur sint occaecat cupidatat non proident").split()

DOMAINS = {
    "business": {
        "subj": ["The team", "Our analysis", "This quarter", "The steering committee", "Customer demand", "The new platform",
                 "Operating margin", "The regional office", "Management", "The pilot program", "Revenue growth", "The supplier network",
                 "Each department", "The board", "Our engineering group", "The marketing function", "Net retention", "The finance team",
                 "Headcount planning", "The product roadmap"],
        "verb": ["improved", "exceeded", "supported", "reduced", "accelerated", "highlighted", "delivered", "maintained", "expanded",
                 "reviewed", "streamlined", "identified", "strengthened", "outlined", "prioritized", "stabilized", "doubled", "tracked"],
        "obj": ["the overall cost structure", "key performance indicators", "the delivery timeline", "customer satisfaction scores",
                "the quarterly forecast", "inventory turnover", "the risk register", "cross-functional collaboration",
                "the onboarding process", "service availability", "average order value", "the hiring pipeline", "gross margin",
                "renewal rates", "the vendor scorecard", "operational resilience", "the capital plan", "support response times"],
        "mod": ["across all regions", "despite supply constraints", "ahead of schedule", "in line with expectations",
                "for the third consecutive quarter", "while keeping headcount flat", "according to preliminary data",
                "compared with the prior year", "within the approved budget", "in the enterprise segment", "after the March release",
                "as planned", "by a significant margin", "in most markets"],
        "conn": ["In addition,", "However,", "As a result,", "Meanwhile,", "Notably,", "Overall,", "At the same time,",
                 "Going forward,", "In particular,", "By contrast,"],
    },
    "legal": {
        "subj": ["The Supplier", "The Customer", "Each Party", "The Contractor", "The Licensee", "The Company", "Neither Party",
                 "The Receiving Party", "The Service Provider", "The Client", "The Disclosing Party", "The Tenant", "The Landlord"],
        "verb": ["shall maintain", "shall not disclose", "shall indemnify", "may terminate", "shall provide", "agrees to deliver",
                 "shall comply with", "shall be liable for", "may assign", "shall promptly notify", "warrants", "shall reimburse"],
        "obj": ["all Confidential Information", "the Services described in Schedule A", "any applicable laws and regulations",
                "the Deliverables", "reasonable records of all transactions", "the fees set out in this Agreement",
                "any third-party claims", "the other Party in writing", "the Premises in good repair", "insurance coverage",
                "the intellectual property rights", "all necessary permits"],
        "mod": ["in accordance with Section 4", "within thirty (30) days", "subject to the limitations herein",
                "during the Term of this Agreement", "upon written notice", "at its own expense", "to the extent permitted by law",
                "without prior written consent", "for a period of two (2) years", "in a timely manner", "as reasonably requested"],
        "conn": ["Notwithstanding the foregoing,", "Furthermore,", "For the avoidance of doubt,", "Subject to clause 9,",
                 "Except as otherwise provided,", "In such event,", "Without limiting the generality of the foregoing,"],
    },
    "academic": {
        "subj": ["We", "Our method", "The proposed model", "Prior work", "This approach", "The baseline", "Our experiments",
                 "The dataset", "The ablation study", "These results", "The encoder", "Recent studies", "The framework"],
        "verb": ["demonstrate", "outperforms", "suggest", "evaluates", "reduces", "improves", "relies on", "extends",
                 "investigate", "achieves", "captures", "generalizes to", "requires"],
        "obj": ["the state of the art", "a significant reduction in error", "robust representations", "the convergence rate",
                "long-range dependencies", "out-of-distribution samples", "a lower computational cost", "the main hypothesis",
                "a held-out test set", "strong inductive biases", "statistically significant gains", "the sampling procedure"],
        "mod": ["on three benchmarks", "under mild assumptions", "with fewer parameters", "across all settings",
                "as shown in Table 2", "in the low-data regime", "compared to previous methods", "by 4.2 points on average",
                "without additional supervision", "as illustrated in Figure 3", "at inference time"],
        "conn": ["Moreover,", "In contrast,", "Specifically,", "Consequently,", "Interestingly,", "To this end,", "Furthermore,",
                 "In practice,", "Empirically,"],
    },
    "marketing": {
        "subj": ["Our new collection", "This season", "Every customer", "Our award-winning team", "The latest release",
                 "Our community", "This exclusive offer", "Our flagship product", "The redesigned app", "Our members"],
        "verb": ["brings", "delivers", "makes", "celebrates", "introduces", "unlocks", "combines", "redefines", "offers", "inspires"],
        "obj": ["effortless style", "unmatched comfort", "real results", "a smarter way to work", "fresh ideas",
                "everything you need", "premium quality", "lasting value", "a seamless experience", "new possibilities"],
        "mod": ["for the whole family", "at an unbeatable price", "every single day", "right at your fingertips",
                "for a limited time", "wherever you are", "without compromise", "in just minutes", "all year round"],
        "conn": ["Best of all,", "Plus,", "And that's not all:", "Whether you're at home or on the go,", "Better yet,", "Even better,"],
    },
    "narrative": {
        "subj": ["The old harbour", "She", "The committee", "Nobody in the village", "The engineer", "Their journey", "The city",
                 "He", "The storm", "The archive", "Every visitor", "The expedition", "Our guide", "The river"],
        "verb": ["remembered", "described", "revealed", "followed", "changed", "crossed", "discovered", "explained", "shaped",
                 "recorded", "abandoned", "rebuilt", "studied", "noticed"],
        "obj": ["the narrow streets", "a forgotten map", "the first winter", "an unexpected letter", "the northern ridge",
                "the long corridor", "a set of instructions", "the morning light", "the original design", "the last train",
                "a quiet garden", "the market square"],
        "mod": ["before dawn", "with great care", "for many years", "without a word", "in the early spring",
                "after the war", "under a grey sky", "at the edge of town", "long after midnight", "by the end of the season"],
        "conn": ["Later,", "Even so,", "In the years that followed,", "For a while,", "Eventually,", "That evening,", "Still,",
                 "Some time afterwards,"],
    },
}


def esc(s):
    return _html.escape(str(s), quote=True)


class Prose:
    def __init__(self, r, domain="business"):
        self.r = r
        self.d = DOMAINS[domain]

    def sentence(self):
        r, d = self.r, self.d
        k = r.random()
        if k < 0.12 and "obj" in d:
            n = r.randint(2, 98)
            return f"{r.choice(d['subj'])} {r.choice(d['verb'])} {r.choice(d['obj'])} by {n}.{r.randint(0, 9)}% {r.choice(d['mod'])}."
        parts = []
        if r.random() < 0.3:
            parts.append(r.choice(d["conn"]))
            s = r.choice(d["subj"])
            if s not in ("We", "He", "She") and not s.startswith(("The S", "The C", "The L", "The T", "The R", "The D", "Neither", "Each")):
                s = s[0].lower() + s[1:]
            parts.append(s)
        else:
            parts.append(r.choice(d["subj"]))
        parts.append(r.choice(d["verb"]))
        parts.append(r.choice(d["obj"]))
        if r.random() < 0.7:
            parts.append(r.choice(d["mod"]))
        if r.random() < 0.25:
            parts.append("and " + r.choice(d["verb"]) + " " + r.choice(d["obj"]))
        return " ".join(parts) + "."

    def para(self, lo=3, hi=6):
        return " ".join(self.sentence() for _ in range(self.r.randint(lo, hi)))

    def words(self, n):
        pool = (" ".join(self.d["obj"] + self.d["mod"])).split()
        return " ".join(self.r.choice(pool) for _ in range(n))

    def title(self, lo=2, hi=5):
        w = [x for x in self.words(self.r.randint(lo, hi)).split() if x not in ("the", "a", "an", "of", "in", "by", "for", "with")]
        if not w:
            w = ["Overview"]
        return " ".join(x[:1].upper() + x[1:] for x in w)


def lorem(r, n):
    return " ".join(r.choice(LOREM) for _ in range(n))


def person(r):
    return f"{r.choice(FIRST)} {r.choice(LAST)}"


def company(r):
    return f"{r.choice(CO_A)} {r.choice(CO_B)}"


def address(r):
    city, zp, country = r.choice(CITIES)
    return [f"{r.randint(1, 980)} {r.choice(STREETS)}", f"{city}, {zp}", country]


def email(r, name, co):
    dom = co.split()[0].lower() + r.choice([".com", ".io", ".co", ".net", ".org"])
    return f"{name.split()[0].lower()}.{name.split()[-1].lower()}@{dom}"


def phone(r):
    return f"+{r.choice([1, 44, 49, 33, 61, 91, 65])} {r.randint(200, 999)} {r.randint(100, 999)} {r.randint(1000, 9999)}"


def date(r, y0=2023, y1=2025):
    return f"{r.choice(MONTHS)} {r.randint(1, 28)}, {r.randint(y0, y1)}"


def iso_date(r, y0=2023, y1=2025):
    return f"{r.randint(y0, y1)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"


def money(v, sym="$", dec=2):
    s = f"{v:,.{dec}f}"
    return f"{sym}{s}"


def page_rule(r, *, sizes=None, margins=None, numbers=0.55, header_text=None, none_prob=0.2, first_blank=0.25, font=None):
    if r.random() < none_prob:
        return ""
    size = r.choice(sizes or ["A4", "A4", "A4 portrait", "Letter", "letter"])
    margin = r.choice(margins or ["20mm", "15mm", "25mm 20mm", "1in", "0.75in", "18mm 16mm 22mm", "2cm", "12mm 14mm", "0.6in 0.5in"])
    boxes = []
    if r.random() < numbers:
        style = f"font-size: {r.choice(['8pt', '9pt', '10px', '11px'])}; color: {r.choice(['#888', '#666', '#999', '#555'])};"
        if font:
            style += f" font-family: {font};"
        v = r.randint(0, 3)
        if v == 0:
            boxes.append(f"@bottom-center {{ content: \"Page \" counter(page) \" of \" counter(pages); {style} }}")
        elif v == 1:
            boxes.append(f"@bottom-right {{ content: counter(page); {style} }}")
        elif v == 2:
            boxes.append(f"@bottom-right {{ content: \"Page \" counter(page); {style} }}")
            if header_text:
                boxes.append(f"@bottom-left {{ content: \"{header_text}\"; {style} }}")
        else:
            boxes.append(f"@bottom-center {{ content: counter(page) \" / \" counter(pages); {style} }}")
            if header_text:
                boxes.append(f"@top-right {{ content: \"{header_text}\"; {style} }}")
    css = f"@page {{\n  size: {size};\n  margin: {margin};\n" + "".join(f"  {b}\n" for b in boxes) + "}\n"
    if boxes and r.random() < first_blank:
        css += "@page :first {\n  @bottom-center { content: none; }\n  @bottom-right { content: none; }\n  @top-right { content: none; }\n}\n"
    return css


PRINT_ADJUST = "@media print {\n  body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }\n  .no-print { display: none !important; }\n}\n"


def util_css(p):
    return f"""
.flex {{ display: flex; }} .inline-flex {{ display: inline-flex; }} .grid {{ display: grid; }} .block {{ display: block; }}
.flex-col {{ flex-direction: column; }} .flex-wrap {{ flex-wrap: wrap; }} .flex-1 {{ flex: 1 1 0%; }}
.items-center {{ align-items: center; }} .items-start {{ align-items: flex-start; }} .items-end {{ align-items: flex-end; }}
.justify-between {{ justify-content: space-between; }} .justify-center {{ justify-content: center; }} .justify-end {{ justify-content: flex-end; }}
.grid-cols-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .grid-cols-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.grid-cols-4 {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }} .col-span-2 {{ grid-column: span 2 / span 2; }}
.gap-1 {{ gap: 0.25rem; }} .gap-2 {{ gap: 0.5rem; }} .gap-3 {{ gap: 0.75rem; }} .gap-4 {{ gap: 1rem; }} .gap-6 {{ gap: 1.5rem; }}
.p-2 {{ padding: 0.5rem; }} .p-3 {{ padding: 0.75rem; }} .p-4 {{ padding: 1rem; }} .p-6 {{ padding: 1.5rem; }} .p-8 {{ padding: 2rem; }}
.px-2 {{ padding-left: 0.5rem; padding-right: 0.5rem; }} .px-3 {{ padding-left: 0.75rem; padding-right: 0.75rem; }} .px-4 {{ padding-left: 1rem; padding-right: 1rem; }}
.py-1 {{ padding-top: 0.25rem; padding-bottom: 0.25rem; }} .py-2 {{ padding-top: 0.5rem; padding-bottom: 0.5rem; }} .py-3 {{ padding-top: 0.75rem; padding-bottom: 0.75rem; }}
.m-0 {{ margin: 0; }} .mt-1 {{ margin-top: 0.25rem; }} .mt-2 {{ margin-top: 0.5rem; }} .mt-4 {{ margin-top: 1rem; }} .mt-6 {{ margin-top: 1.5rem; }} .mt-8 {{ margin-top: 2rem; }}
.mb-1 {{ margin-bottom: 0.25rem; }} .mb-2 {{ margin-bottom: 0.5rem; }} .mb-4 {{ margin-bottom: 1rem; }} .mb-6 {{ margin-bottom: 1.5rem; }} .ml-auto {{ margin-left: auto; }}
.text-xs {{ font-size: 0.75rem; line-height: 1rem; }} .text-sm {{ font-size: 0.875rem; line-height: 1.25rem; }} .text-base {{ font-size: 1rem; line-height: 1.5rem; }}
.text-lg {{ font-size: 1.125rem; line-height: 1.75rem; }} .text-xl {{ font-size: 1.25rem; line-height: 1.75rem; }} .text-2xl {{ font-size: 1.5rem; line-height: 2rem; }}
.text-3xl {{ font-size: 1.875rem; line-height: 2.25rem; }} .text-4xl {{ font-size: 2.25rem; line-height: 2.5rem; }}
.font-medium {{ font-weight: 500; }} .font-semibold {{ font-weight: 600; }} .font-bold {{ font-weight: 700; }} .italic {{ font-style: italic; }}
.uppercase {{ text-transform: uppercase; }} .tracking-wide {{ letter-spacing: 0.05em; }} .tracking-wider {{ letter-spacing: 0.1em; }}
.text-left {{ text-align: left; }} .text-center {{ text-align: center; }} .text-right {{ text-align: right; }} .leading-tight {{ line-height: 1.25; }} .leading-relaxed {{ line-height: 1.625; }}
.text-white {{ color: #fff; }} .text-muted {{ color: {p['muted']}; }} .text-primary {{ color: {p['primary']}; }} .text-accent {{ color: {p['accent']}; }} .text-dark {{ color: {p['dark']}; }}
.text-green {{ color: #16a34a; }} .text-red {{ color: #dc2626; }}
.bg-white {{ background-color: #fff; }} .bg-soft {{ background-color: {p['soft']}; }} .bg-primary {{ background-color: {p['primary']}; }} .bg-dark {{ background-color: {p['dark']}; }}
.border {{ border: 1px solid {p['border']}; }} .border-b {{ border-bottom: 1px solid {p['border']}; }} .border-t {{ border-top: 1px solid {p['border']}; }} .border-l-4 {{ border-left: 4px solid {p['primary']}; }}
.rounded {{ border-radius: 0.25rem; }} .rounded-md {{ border-radius: 0.375rem; }} .rounded-lg {{ border-radius: 0.5rem; }} .rounded-xl {{ border-radius: 0.75rem; }} .rounded-full {{ border-radius: 9999px; }}
.shadow {{ box-shadow: 0 1px 3px 0 rgba(0,0,0,.1), 0 1px 2px -1px rgba(0,0,0,.1); }} .shadow-md {{ box-shadow: 0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1); }}
.shadow-lg {{ box-shadow: 0 10px 15px -3px rgba(0,0,0,.1), 0 4px 6px -4px rgba(0,0,0,.1); }}
.w-full {{ width: 100%; }} .w-1\\/2 {{ width: 50%; }} .w-1\\/3 {{ width: 33.333333%; }} .w-2\\/3 {{ width: 66.666667%; }} .h-2 {{ height: 0.5rem; }}
.overflow-hidden {{ overflow: hidden; }} .relative {{ position: relative; }} .absolute {{ position: absolute; }}
.space-y-2 > * + * {{ margin-top: 0.5rem; }} .space-y-4 > * + * {{ margin-top: 1rem; }}
.divide-y > * + * {{ border-top: 1px solid {p['border']}; }}
.break-inside-avoid {{ break-inside: avoid; page-break-inside: avoid; }} .break-before-page {{ break-before: page; page-break-before: always; }}
"""


def _nice_max(v):
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


def _fmt(v):
    if abs(v) >= 1000:
        return f"{v / 1000:.0f}k" if v % 1000 == 0 else f"{v / 1000:.1f}k"
    return f"{v:g}"


def svg_bar(r, p, labels, series, names=None, w=560, h=260, horizontal=False, stacked=False, title=None, responsive=None):
    cols = p["series"]
    pad_l, pad_r, pad_t, pad_b = 46, 12, 28 if title else 12, 34
    if names and len(series) > 1:
        pad_t += 18
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(labels)
    vmax = _nice_max(max(sum(s[i] for s in series) for i in range(n)) if stacked else max(max(s) for s in series))
    out = []
    if responsive is None:
        responsive = r.random() < 0.5
    size = f'viewBox="0 0 {w} {h}" width="100%"' if responsive else f'width="{w}" height="{h}" viewBox="0 0 {w} {h}"'
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" {size} font-size="11" role="img">')
    if title:
        out.append(f'<text x="{pad_l}" y="16" font-size="13" font-weight="bold" fill="{p["text"]}">{esc(title)}</text>')
    if names and len(series) > 1:
        x = pad_l
        for k, nm in enumerate(names):
            out.append(f'<rect x="{x}" y="{pad_t - 26}" width="10" height="10" rx="2" fill="{cols[k % len(cols)]}"/>'
                       f'<text x="{x + 14}" y="{pad_t - 17}" fill="{p["muted"]}">{esc(nm)}</text>')
            x += 22 + 7 * len(nm)
    ticks = 4
    for t in range(ticks + 1):
        v = vmax * t / ticks
        if horizontal:
            x = pad_l + cw * t / ticks
            out.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + ch}" stroke="#e5e7eb"/>'
                       f'<text x="{x:.1f}" y="{pad_t + ch + 14}" text-anchor="middle" fill="{p["muted"]}">{_fmt(v)}</text>')
        else:
            y = pad_t + ch - ch * t / ticks
            out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + cw}" y2="{y:.1f}" stroke="#e5e7eb"/>'
                       f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" fill="{p["muted"]}">{_fmt(v)}</text>')
    slot = (ch if horizontal else cw) / n
    gw = slot * 0.7
    for i, lab in enumerate(labels):
        base = 0
        for k, s in enumerate(series):
            v = s[i]
            if stacked:
                bw = gw
                off = 0
            else:
                bw = gw / len(series)
                off = bw * k
            L = (v / vmax) * (cw if horizontal else ch)
            col = cols[k % len(cols)]
            if horizontal:
                y = pad_t + slot * i + (slot - gw) / 2 + off
                x = pad_l + (base / vmax) * cw
                out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{L:.1f}" height="{bw - 1:.1f}" rx="2" fill="{col}"/>')
            else:
                x = pad_l + slot * i + (slot - gw) / 2 + off
                y = pad_t + ch - (base / vmax) * ch - L
                out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw - 1:.1f}" height="{L:.1f}" rx="2" fill="{col}"/>')
            if stacked:
                base += v
        if horizontal:
            out.append(f'<text x="{pad_l - 6}" y="{pad_t + slot * i + slot / 2 + 4:.1f}" text-anchor="end" fill="{p["text"]}">{esc(lab)}</text>')
        else:
            out.append(f'<text x="{pad_l + slot * i + slot / 2:.1f}" y="{pad_t + ch + 16}" text-anchor="middle" fill="{p["text"]}">{esc(lab)}</text>')
    out.append(f'<line x1="{pad_l}" y1="{pad_t + ch}" x2="{pad_l + cw}" y2="{pad_t + ch}" stroke="{p["muted"]}"/>')
    out.append("</svg>")
    return "".join(out)


def svg_line(r, p, labels, series, names=None, w=560, h=240, area=False, title=None, responsive=None):
    cols = p["series"]
    pad_l, pad_r, pad_t, pad_b = 46, 14, 28 if title else 14, 30
    if names:
        pad_t += 16
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    vmax = _nice_max(max(max(s) for s in series))
    if responsive is None:
        responsive = r.random() < 0.5
    size = f'viewBox="0 0 {w} {h}" width="100%"' if responsive else f'width="{w}" height="{h}" viewBox="0 0 {w} {h}"'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" {size} font-size="11" role="img">']
    if title:
        out.append(f'<text x="{pad_l}" y="16" font-size="13" font-weight="bold" fill="{p["text"]}">{esc(title)}</text>')
    if names:
        x = pad_l
        for k, nm in enumerate(names):
            out.append(f'<line x1="{x}" y1="{pad_t - 18}" x2="{x + 14}" y2="{pad_t - 18}" stroke="{cols[k % len(cols)]}" stroke-width="3"/>'
                       f'<text x="{x + 18}" y="{pad_t - 14}" fill="{p["muted"]}">{esc(nm)}</text>')
            x += 26 + 7 * len(nm)
    for t in range(5):
        y = pad_t + ch - ch * t / 4
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + cw}" y2="{y:.1f}" stroke="#eceff3"/>'
                   f'<text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" fill="{p["muted"]}">{_fmt(vmax * t / 4)}</text>')
    n = len(labels)
    step = cw / max(n - 1, 1)
    for i, lab in enumerate(labels):
        if n <= 12 or i % 2 == 0:
            out.append(f'<text x="{pad_l + step * i:.1f}" y="{pad_t + ch + 16}" text-anchor="middle" fill="{p["text"]}">{esc(lab)}</text>')
    for k, s in enumerate(series):
        col = cols[k % len(cols)]
        pts = [(pad_l + step * i, pad_t + ch - (v / vmax) * ch) for i, v in enumerate(s)]
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if area:
            out.append(f'<polygon points="{pad_l},{pad_t + ch} {d} {pts[-1][0]:.1f},{pad_t + ch}" fill="{col}" fill-opacity="0.15"/>')
        out.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round"/>')
        if n <= 14:
            for x, y in pts:
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#fff" stroke="{col}" stroke-width="2"/>')
    out.append("</svg>")
    return "".join(out)


def svg_pie(r, p, labels, values, size=220, donut=False, legend=True, title=None):
    cols = p["series"] + ["#94a3b8", "#cbd5e1", "#475569"]
    tot = float(sum(values)) or 1.0
    lw = 170 if legend else 0
    W, H = size + lw, size + (22 if title else 0)
    oy = 22 if title else 0
    cx, cy, R = size / 2, oy + size / 2, size / 2 - 6
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-size="11" role="img">']
    if title:
        out.append(f'<text x="4" y="15" font-size="13" font-weight="bold" fill="{p["text"]}">{esc(title)}</text>')
    a0 = -math.pi / 2
    for i, v in enumerate(values):
        a1 = a0 + 2 * math.pi * v / tot
        large = 1 if a1 - a0 > math.pi else 0
        x0, y0 = cx + R * math.cos(a0), cy + R * math.sin(a0)
        x1, y1 = cx + R * math.cos(a1), cy + R * math.sin(a1)
        col = cols[i % len(cols)]
        if v / tot > 0.999:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="{col}"/>')
        else:
            out.append(f'<path d="M{cx:.1f},{cy:.1f} L{x0:.1f},{y0:.1f} A{R:.1f},{R:.1f} 0 {large} 1 {x1:.1f},{y1:.1f} Z" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
        a0 = a1
    if donut:
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{R * 0.58:.1f}" fill="#fff"/>'
                   f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="18" font-weight="bold" fill="{p["text"]}">{_fmt(tot)}</text>'
                   f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" fill="{p["muted"]}">total</text>')
    if legend:
        for i, (lab, v) in enumerate(zip(labels, values)):
            y = oy + 18 + i * 20
            out.append(f'<rect x="{size + 10}" y="{y - 9}" width="10" height="10" rx="2" fill="{cols[i % len(cols)]}"/>'
                       f'<text x="{size + 26}" y="{y}" fill="{p["text"]}">{esc(lab)} ({100 * v / tot:.1f}%)</text>')
    out.append("</svg>")
    return "".join(out)


def svg_spark(r, color, n=12, w=120, h=32):
    vals = [r.uniform(10, 30)]
    for _ in range(n - 1):
        vals.append(max(1, vals[-1] + r.uniform(-5, 6)))
    mx, mn = max(vals), min(vals)
    pts = " ".join(f"{i * w / (n - 1):.1f},{h - 3 - (v - mn) / ((mx - mn) or 1) * (h - 6):.1f}" for i, v in enumerate(vals))
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/></svg>'


def svg_logo(r, p, text, size=44):
    k = r.randint(0, 3)
    ini = "".join(w[0] for w in text.split()[:2]).upper()
    if k == 0:
        shape = f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2}" fill="{p["primary"]}"/>'
    elif k == 1:
        shape = f'<rect width="{size}" height="{size}" rx="{size / 4}" fill="{p["primary"]}"/>'
    elif k == 2:
        shape = (f'<polygon points="{size / 2},0 {size},{size} 0,{size}" fill="{p["primary"]}"/>')
        return f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">{shape}</svg>'
    else:
        shape = (f'<defs><linearGradient id="lg{r.randint(0, 99999)}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p["primary"]}"/>'
                 f'<stop offset="1" stop-color="{p["accent"]}"/></linearGradient></defs>')
        gid = shape.split('id="')[1].split('"')[0]
        shape += f'<rect width="{size}" height="{size}" rx="{size / 2}" fill="url(#{gid})"/>'
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">{shape}'
            f'<text x="{size / 2}" y="{size / 2 + size / 7:.1f}" text-anchor="middle" font-size="{size * 0.4:.0f}" font-weight="bold" fill="#fff" font-family="Arial, sans-serif">{esc(ini)}</text></svg>')


def svg_barcode(r, w=220, h=50, text=None):
    x = 0
    bars = []
    while x < w - 4:
        bw = r.choice([1, 1, 2, 3])
        if r.random() < 0.55:
            bars.append(f'<rect x="{x}" y="0" width="{bw}" height="{h - (14 if text else 0)}" fill="#000"/>')
        x += bw
    t = f'<text x="{w / 2}" y="{h - 2}" text-anchor="middle" font-size="11" font-family="monospace">{esc(text)}</text>' if text else ""
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">{"".join(bars)}{t}</svg>'


def svg_qr(r, n=21, cell=4):
    s = n * cell
    out = [f'<svg width="{s}" height="{s}" viewBox="0 0 {s} {s}"><rect width="{s}" height="{s}" fill="#fff"/>']
    for y in range(n):
        for x in range(n):
            finder = any(x0 <= x < x0 + 7 and y0 <= y < y0 + 7 for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)))
            if finder:
                fx = x if x < 7 else x - (n - 7)
                fy = y if y < 7 else y - (n - 7)
                on = fx in (0, 6) or fy in (0, 6) or (2 <= fx <= 4 and 2 <= fy <= 4)
            else:
                on = r.random() < 0.5
            if on:
                out.append(f'<rect x="{x * cell}" y="{y * cell}" width="{cell}" height="{cell}"/>')
    out.append("</svg>")
    return "".join(out)


def svg_placeholder(r, p, w, h, label=None):
    gid = f"g{r.randint(0, 999999)}"
    lab = f'<text x="{w / 2}" y="{h / 2 + 5}" text-anchor="middle" font-size="14" fill="#fff" font-family="Arial, sans-serif">{esc(label)}</text>' if label else ""
    return (f'<svg width="100%" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{p["primary"]}"/><stop offset="1" stop-color="{p["accent"]}"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#{gid})"/><circle cx="{w * 0.75:.0f}" cy="{h * 0.3:.0f}" r="{h * 0.18:.0f}" fill="#fff" fill-opacity="0.25"/>'
            f'<polygon points="0,{h} {w * 0.35:.0f},{h * 0.45:.0f} {w * 0.6:.0f},{h} " fill="#000" fill-opacity="0.15"/>{lab}</svg>')


def html_doc(title, css, body, lang="en", dirn=None, head_extra=""):
    d = f' dir="{dirn}"' if dirn else ""
    return (f'<!DOCTYPE html>\n<html lang="{lang}"{d}>\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>{esc(title)}</title>\n{head_extra}'
            f'<style>\n{css}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n')

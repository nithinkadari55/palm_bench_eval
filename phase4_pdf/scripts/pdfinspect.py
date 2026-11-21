"""Shared PDF inspection helpers for structure_check.py and navigation_check.py (pikepdf, pypdf, pdfminer.six)."""
import unicodedata

import pikepdf
import pypdf
from pdfminer.pdfdevice import PDFDevice
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.psparser import PSLiteral
from pdfminer.utils import decode_text


def norm(s):
    return " ".join(unicodedata.normalize("NFC", s or "").split())


def _lit(v):
    if isinstance(v, PSLiteral):
        return v.name if isinstance(v.name, str) else v.name.decode("latin-1")
    if isinstance(v, bytes):
        return decode_text(v)
    return v


class MarkedContentDevice(PDFDevice):
    """Collects text per marked-content id, artifact text and untagged text, honouring /ActualText."""

    def __init__(self, rsrcmgr):
        super().__init__(rsrcmgr)
        self.stack = []
        self.pages = []
        self.cur = None
        self._actual_done = set()

    def begin_page(self, page, ctm):
        self.cur = {"mcid": {}, "mcid_raw": {}, "artifacts": [], "untagged": ""}
        self.stack = []

    def end_page(self, page):
        self.pages.append(self.cur)

    def begin_tag(self, tag, props=None):
        name = _lit(tag)
        p = {k: _lit(v) for k, v in props.items()} if isinstance(props, dict) else {}
        self.stack.append((name, p, len(self.stack), id(p)))

    def end_tag(self):
        if self.stack:
            self.stack.pop()

    def do_tag(self, tag, props=None):
        pass

    def render_string(self, textstate, seq, ncs, graphicstate):
        font = textstate.font
        raw = ""
        if font is not None:
            for obj in seq:
                if isinstance(obj, bytes):
                    for cid in font.decode(obj):
                        try:
                            raw += font.to_unichr(cid)
                        except Exception:
                            raw += "�"
        logical = raw
        for name, p, _, key in self.stack:
            if "ActualText" in p:
                logical = "" if key in self._actual_done else str(p["ActualText"])
                self._actual_done.add(key)
                break
        mcid, art = None, None
        for name, p, _, _ in reversed(self.stack):
            if mcid is None and "MCID" in p:
                mcid = p["MCID"]
            if name == "Artifact" and art is None:
                art = p
        if art is not None:
            self.cur["artifacts"].append({"props": {k: str(v) for k, v in art.items()}, "text": logical})
        elif mcid is not None:
            self.cur["mcid"][mcid] = self.cur["mcid"].get(mcid, "") + logical
            self.cur["mcid_raw"][mcid] = self.cur["mcid_raw"].get(mcid, "") + raw
        else:
            self.cur["untagged"] += logical


def marked_content(path):
    rsrc = PDFResourceManager()
    dev = MarkedContentDevice(rsrc)
    interp = PDFPageInterpreter(rsrc, dev)
    with open(path, "rb") as f:
        for page in PDFPage.get_pages(f):
            interp.process_page(page)
    return dev.pages


def _number_tree(node, out):
    if node is None:
        return out
    if "/Nums" in node:
        nums = node["/Nums"]
        for i in range(0, len(nums), 2):
            out[int(nums[i])] = nums[i + 1]
    for kid in node.get("/Kids", []):
        _number_tree(kid, out)
    return out


def _attrs(a):
    out = []
    if a is None:
        return out
    items = a if isinstance(a, pikepdf.Array) else [a]
    for it in items:
        if isinstance(it, pikepdf.Dictionary):
            out.append({str(k): (str(v) if not isinstance(v, (int, float)) else v) for k, v in it.items()})
    return out


def struct_tree_pikepdf(pdf):
    """Returns (elements in DFS pre-order, leaf sequence, info)."""
    root = pdf.Root.get("/StructTreeRoot")
    if root is None:
        return None
    rolemap = root.get("/RoleMap", pikepdf.Dictionary())
    page_of = {p.obj.objgen: i for i, p in enumerate(pdf.pages)}
    elems, leaves = [], []

    def resolve(role):
        seen = set()
        while ("/" + role) in rolemap and role not in seen:
            seen.add(role)
            role = str(rolemap["/" + role])[1:]
        return role

    def visit(node, depth, pg, parent_idx):
        if node is None:
            return
        if isinstance(node, pikepdf.Array):
            for k in node:
                visit(k, depth, pg, parent_idx)
            return
        if isinstance(node, (int, pikepdf.Object)) and not isinstance(node, pikepdf.Dictionary):
            try:
                mcid = int(node)
            except Exception:
                return
            if parent_idx is None:
                return
            leaves.append({"kind": "mcid", "page": pg, "mcid": mcid, "elem": parent_idx})
            elems[parent_idx]["mcids"].append((pg, mcid))
            return
        if not isinstance(node, pikepdf.Dictionary):
            return
        t = str(node.get("/Type", ""))
        if t in ("/MCR", "/OBJR") and parent_idx is None:
            return
        if t == "/MCR":
            p = page_of.get(node["/Pg"].objgen, pg) if "/Pg" in node else pg
            leaves.append({"kind": "mcid", "page": p, "mcid": int(node["/MCID"]), "elem": parent_idx})
            elems[parent_idx]["mcids"].append((p, int(node["/MCID"])))
            return
        if t == "/OBJR":
            obj = node.get("/Obj")
            leaves.append({"kind": "objr", "elem": parent_idx, "objgen": obj.objgen if obj is not None else None})
            elems[parent_idx]["objr"].append(obj.objgen if obj is not None else None)
            return
        if "/S" not in node:
            return
        role = str(node["/S"])[1:]
        p = page_of.get(node["/Pg"].objgen, pg) if "/Pg" in node and hasattr(node["/Pg"], "objgen") else pg
        e = {
            "role": role, "std": resolve(role), "depth": depth, "page": p, "objgen": node.objgen,
            "alt": str(node["/Alt"]) if "/Alt" in node else None,
            "lang": str(node["/Lang"]) if "/Lang" in node else None,
            "title": str(node["/T"]) if "/T" in node else None,
            "actual_text": str(node["/ActualText"]) if "/ActualText" in node else None,
            "attrs": _attrs(node.get("/A")), "mcids": [], "objr": [], "parent": parent_idx,
        }
        elems.append(e)
        idx = len(elems) - 1
        if "/K" in node:
            visit(node["/K"], depth + 1, p, idx)

    visit(root.get("/K"), 0, None, None)
    parent_tree = _number_tree(root.get("/ParentTree"), {})
    info = {"rolemap": {str(k): str(v) for k, v in rolemap.items()}, "parent_tree_keys": len(parent_tree)}
    return elems, leaves, parent_tree, info


def struct_roles_pypdf(path):
    """Independent walk with pypdf: DFS pre-order list of (role, depth, alt)."""
    r = pypdf.PdfReader(path)
    root = r.trailer["/Root"].get_object()
    st = root.get("/StructTreeRoot")
    if st is None:
        return None
    st = st.get_object()
    out = []

    def visit(node, depth):
        node = node.get_object() if hasattr(node, "get_object") else node
        if isinstance(node, pypdf.generic.ArrayObject):
            for k in node:
                visit(k, depth)
            return
        if isinstance(node, pypdf.generic.DictionaryObject):
            if "/S" in node:
                out.append((str(node["/S"])[1:], depth, str(node["/Alt"]) if "/Alt" in node else None))
                if "/K" in node:
                    visit(node["/K"], depth + 1)

    if "/K" in st:
        visit(st["/K"], 0)
    return out


def page_labels(path):
    try:
        return list(pypdf.PdfReader(path).page_labels)
    except Exception as e:
        return [f"error: {e!r}"]

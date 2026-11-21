#!/usr/bin/env python3
"""Shared helpers for the phase 3 media tests."""
import hashlib
import json
import os
import struct
import subprocess
import sys

import numpy as np

MAX_FAILURES = 20


def read_raw(path):
    """Read a P3R1 file written by p3common::write_raw. Returns (frames, h, w, c) uint8/uint16."""
    with open(path, "rb") as fh:
        buf = fh.read()
    if len(buf) < 16 or buf[:4] != b"P3R1":
        raise ValueError("not a P3R1 file")
    w, h = struct.unpack_from("<II", buf, 4)
    c, depth = buf[12], buf[13]
    n = struct.unpack_from("<H", buf, 14)[0]
    dt = np.dtype("<u2") if depth == 16 else np.uint8
    arr = np.frombuffer(buf, dtype=dt, offset=16)
    if arr.size != n * h * w * c:
        raise ValueError("P3R1 size mismatch")
    return arr.reshape(n, h, w, c).astype(np.uint16 if depth == 16 else np.uint8)


def write_raw(path, arr):
    """arr: (h, w, c) or (frames, h, w, c), uint8 or uint16."""
    a = np.asarray(arr)
    if a.ndim == 3:
        a = a[None]
    n, h, w, c = a.shape
    depth = 16 if a.dtype == np.uint16 else 8
    with open(path, "wb") as fh:
        fh.write(b"P3R1" + struct.pack("<IIBBH", w, h, c, depth, n))
        fh.write(a.astype("<u2" if depth == 16 else np.uint8).tobytes())


def to_unit(a):
    """uint8/uint16 array -> float64 in [0, 1]."""
    a = np.asarray(a)
    if a.dtype == np.uint16:
        return a.astype(np.float64) / 65535.0
    return a.astype(np.float64) / 255.0


def flatten_on_white(rgba_unit):
    rgb = rgba_unit[..., :3]
    a = rgba_unit[..., 3:4]
    return rgb * a + (1.0 - a)


# ---------- colour difference ----------

_M_SRGB_XYZ_D65 = np.array([
    [0.4123907992659595, 0.357584339383878, 0.1804807884018343],
    [0.21263900587151036, 0.715168678767756, 0.07219231536073371],
    [0.01933081871559185, 0.11919477979462598, 0.9505321522496606],
])
_WHITE_D65 = np.array([0.3127 / 0.3290, 1.0, (1.0 - 0.3127 - 0.3290) / 0.3290])


def srgb_to_lab(rgb_unit):
    """sRGB in [0,1] (..., 3) -> CIE Lab with D65 reference white."""
    c = np.asarray(rgb_unit, dtype=np.float64)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M_SRGB_XYZ_D65.T
    t = xyz / _WHITE_D65
    eps, kappa = 216 / 24389, 24389 / 27
    f = np.where(t > eps, np.cbrt(t), (kappa * t + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def delta_e2000(lab1, lab2):
    """CIEDE2000 (Sharma, Wu, Dalal 2005), vectorised."""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dh = h2p - h1p
    dh = np.where(C1p * C2p == 0, 0, np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh) / 2)
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(C1p * C2p == 0, hs,
                   np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dtheta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc = 1 + 0.045 * Cbp
    Sh = 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def de2000_srgb(rgb1_unit, rgb2_unit):
    return delta_e2000(srgb_to_lab(rgb1_unit), srgb_to_lab(rgb2_unit))


def de_stats(de):
    de = np.asarray(de, dtype=np.float64).ravel()
    if de.size == 0:
        return {"mean": None, "p95": None, "max": None}
    return {"mean": round(float(de.mean()), 4), "p95": round(float(np.percentile(de, 95)), 4),
            "max": round(float(de.max()), 4)}


def diff_stats(a_unit, b_unit, scale=255.0):
    """Channel-difference statistics on an 8-bit scale."""
    d = np.abs(np.asarray(a_unit, np.float64) - np.asarray(b_unit, np.float64)) * scale
    if d.size == 0:
        return {"mean_abs": 0.0, "max_abs": 0.0, "pct_gt3": 0.0}
    return {"mean_abs": round(float(d.mean()), 4), "max_abs": round(float(d.max()), 3),
            "pct_gt3": round(100.0 * float((d.max(axis=-1) > 3.0).mean()), 4)}


# ---------- results ----------

def write_result(path, name, criterion, cases, extra=None):
    """cases: list of dicts with key 'pass' (bool). Failures keep their details (first 20)."""
    total = len(cases)
    npass = sum(1 for c in cases if c.get("pass"))
    fails = [c for c in cases if not c.get("pass")]
    doc = {"test": name, "pass": npass, "fail": total - npass, "total": total,
           "pass_rate": (npass / total) if total else None, "pass_criterion": criterion,
           "first_failures": fails[:MAX_FAILURES]}
    if extra:
        doc.update(extra)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, default=_json_default)
    print(f"{name}: {npass}/{total} pass", file=sys.stderr)
    return doc


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(repr(o))


def run_batch(exe, sub, cases, manifest_path, results_path, timeout_ms=20000, jobs=None):
    """cases: list of {'id','input','out','args'}; returns {id: result}."""
    os.makedirs(os.path.dirname(os.path.abspath(manifest_path)), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"cases": cases}, fh)
    cmd = [exe, "batch", sub, manifest_path, results_path, str(timeout_ms)]
    if jobs:
        cmd.append(str(jobs))
    subprocess.run(cmd, check=True)
    with open(results_path, encoding="utf-8") as fh:
        res = json.load(fh)["results"]
    return {r["id"]: r for r in res if r}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default

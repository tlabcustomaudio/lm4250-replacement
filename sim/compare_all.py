"""One comparison for every candidate, same circuit (Stingray-style preamp pedal V3, R7 1M5, 9 V), same grid, same bursts, same metrics vs the LM4250 reference.
Metrics (all vs REF = datasheet-curve model with 2 poles):
  ac_w   worst |dB| over the control grid, 40 Hz-16 kHz        ac_r  rms dB (same range)       ac_hi worst |dB| 16-20 kHz
  lvl    mean |dB| of the fundamental level in the large-signal bursts (RV1 max)     thd   mean |dB| of the distortion difference in those bursts
usage: LM_VS=9 uv run --with numpy python compare_all.py"""
import json, math, os, re, sys
import numpy as np
import emu, study, spice, bench2, module

VS = 9.0
CASES = [dict(RV1=a, RV2=b, RV3=1) for a in (0, .25, .5, .75, 1) for b in (0, .5, 1)]
BURSTS = [(10000, 0.12), (10000, 0.3), (5000, 0.5), (2000, 1.0)]


def fixed(name, gbw, sr, ib, hr):
    return bench2.fixed_sub(gbw, sr, hr).replace("FIX", name).replace(".subckt " + name + " inp inn vp vn out iset", ".subckt " + name + " inp inn vp vn out iset") + f"\n"


# name: (subckt text, U1 line, C6 value or None, consumption uA at 9 V, note)
LINE5 = "XU1 {n3} {n2} {n7} {n4} {n6} %s"
LINE6 = "XU1 {n3} {n2} {n7} {n4} {n6} {n8} %s"
CANDS = {
    "LM4250 reference (2 poles)": (None, LINE5 % "REF", None, 46, "datasheet curves"),
    "Discrete clone (Cc 40 pF)": (bench2.CLONE_SUB.replace("Cc d2 h 36p", "Cc d2 h 40p") if "36p" in bench2.CLONE_SUB else bench2.CLONE_SUB, "XU1 {n2} {n3} {n7} {n4} {n6} {n8} LM4250", None, 71, "transistor level"),
    "OTA emulator (LM13700-type)": (None, LINE5 % "EMU", None, 5000, "behavioural"),
    "LM308 + 100 pF (pins 1-8)": (fixed("LM308A", 0.3e6, 0.09e6, 1.5e-9, 2.0), LINE6 % "LM308A", None, 300, "1 MHz/0.3 V/us at 30 pF, scaled"),
    "LM308 + 150 pF (pins 1-8)": (fixed("LM308B", 0.2e6, 0.06e6, 1.5e-9, 2.0), LINE6 % "LM308B", None, 300, "idem"),
    "TLC271 medium (pin 8 = pin 3)": (fixed("TLC271M", 0.5e6, 0.43e6, 1e-12, 0.5), LINE6 % "TLC271M", None, 150, "datasheet 0.5 MHz/0.43"),
    "OPA333 module (LDO window 2-7 V)": (None, LINE5 % "MODULE", None, 28, "module.py"),
    "OP07": (fixed("OP07X", 0.6e6, 0.3e6, 2e-9, 2.0), LINE6 % "OP07X", "100p", 3500, "0.6 MHz/0.3 V/us"),
    "TL061 + C6 100p": (fixed("TL061X", 1e6, 3.5e6, 30e-12, 1.5), LINE6 % "TL061X", "100p", 200, "1 MHz/3.5 V/us"),
    "TL071 + C6 82p": (fixed("TL071X", 3e6, 13e6, 65e-12, 1.5), LINE6 % "TL071X", "82p", 1400, "3 MHz/13 V/us"),
}


def models(extra):
    return extra or ""


def build(name):
    sub, line, c6, _, _ = CANDS[name]
    xml = open(study.HERE + "/mm_v3.xml").read()
    p = spice.parse(re.sub(r"(\d),(\d)", r"\1.\2", xml))
    ov = {r: "skip" for r in "J3 D2 R22 N1 S1 SW1".split()}
    ov["U1"] = line
    if c6:
        ov["C6"] = c6
    orig, old = spice.lines, spice.MODELS
    spice.lines = lambda *a: orig(*a) + study.extra(p, 1)
    spice.MODELS = old + emu.EMU + emu.REF + (sub or "")
    return p, ov, orig, old


def ac(name, st):
    p, ov, orig, old = build(name)
    try:
        return np.array(spice.ac(p, st, ov, {"+VDC": VS}, 40, 20000, 30))
    finally:
        spice.lines, spice.MODELS = orig, old


def tran(name, x, sr):
    p, ov, orig, old = build(name)
    try:
        return np.array(spice.tran(p, list(x), sr, settings=dict(RV1=1, RV2=.5, RV3=1), overrides=ov, supplies={"+VDC": VS}, rs=1e3))
    finally:
        spice.lines, spice.MODELS = orig, old


def fund_thd(y, f, sr):
    y = y[len(y) // 2:]; y = y - y.mean(); t = np.arange(len(y)) / sr
    n = int(len(y) / (sr / f)) * (sr / f); k = int(round(n)); y, t = y[:k], t[:k]
    a = 2 * np.mean(y * np.sin(2 * np.pi * f * t)); b = 2 * np.mean(y * np.cos(2 * np.pi * f * t))
    a1 = math.hypot(a, b); res = y - a * np.sin(2 * np.pi * f * t) - b * np.cos(2 * np.pi * f * t)
    return 20 * math.log10(a1 + 1e-12), 20 * math.log10(np.sqrt(np.mean(res ** 2)) / (a1 / math.sqrt(2)) + 1e-12)


if __name__ == "__main__":
    ref_ac = [ac("LM4250 reference (2 poles)", st) for st in CASES]
    sr = 960000
    xs = []
    for f, amp in BURSTS:
        n = int(0.004 * sr)
        xs.append(amp * np.sin(2 * np.pi * f * np.arange(n) / sr) * np.minimum(1, np.arange(n) / (0.0005 * sr)))
    ref_tr = [fund_thd(tran("LM4250 reference (2 poles)", x, sr), f, sr) for x, (f, _) in zip(xs, BURSTS)]
    rows = {}
    for name in CANDS:
        if name.startswith("LM4250 ref"):
            continue
        a = [ac(name, st) for st in CASES]
        d = np.array([x[:, 1] - r[:, 1] for x, r in zip(a, ref_ac)]); fr = ref_ac[0][:, 0]
        mid, hi = (fr <= 16000), (fr > 16000)
        tr = [fund_thd(tran(name, x, sr), f, sr) for x, (f, _) in zip(xs, BURSTS)]
        rows[name] = dict(ac_w=float(np.abs(d[:, mid]).max()), ac_r=float(np.sqrt((d[:, mid] ** 2).mean())), ac_hi=float(np.abs(d[:, hi]).max()),
                          lvl=float(np.mean([abs(t[0] - r[0]) for t, r in zip(tr, ref_tr)])), thd=float(np.mean([abs(t[1] - r[1]) for t, r in zip(tr, ref_tr)])),
                          tr=[(round(t[0], 1), round(t[1], 1)) for t in tr], ua=CANDS[name][3])
        r = rows[name]
        print(f"{name:34s} ac_w {r['ac_w']:5.2f}  ac_rms {r['ac_r']:4.2f}  ac_16-20k {r['ac_hi']:5.2f}  lvl {r['lvl']:4.2f}  thd {r['thd']:5.2f}  uA {r['ua']}", flush=True)
        json.dump(dict(ref_tr=ref_tr, rows=rows), open("../data/compare_all.json", "w"), indent=1)

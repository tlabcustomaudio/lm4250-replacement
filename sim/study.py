"""Stingray-style Stomp (V3): LM4250 (Iset ~5.7 uA: GBW 200 kHz, SR ~0.13 V/us, PNP input) vs candidate op-amps in the same circuit.
   uv run --with numpy python lm4250/study.py   (needs ngspice on PATH: micromamba env spice)"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import spice

HERE = os.path.dirname(os.path.abspath(__file__))
OPX = """
.subckt OPX inp inn vp vn out params: gbw=1Meg sr=1Meg ib=0 hr=1.5
* one-pole op-amp: 100 dB DC gain, gm limited by tanh (slew = sr), bias current ib out of both inputs, output hr volts inside the rails
.param imax={sr*1e-3/(6.2832*gbw)}
B1 0 n1 I = imax*tanh(1e-3*(v(inp)-v(inn))/imax)
R1 n1 0 1e8
C1 n1 0 {1e-3/(6.2832*gbw)}
Bo n2 0 V = max(min(v(n1), v(vp)-hr), v(vn)+hr)
Ro n2 out 50
Rq vp vn 5k
Ib1 vp inp DC {ib}
Ib2 vp inn DC {ib}
.ends
"""
CANDS = {  # name: (gbw, slew V/s, ib, headroom)
    "LM4250@5.7uA": ("200k", 0.13e6, 15e-9, 1.5),
    "TL071": ("3Meg", 13e6, 65e-12, 1.5),
    "TLC271 medium": ("525k", 0.43e6, 1e-12, 0.5),
    "TLC271 low": ("85k", 0.03e6, 1e-12, 0.5),
}
SW = {"S1": [("1", "2"), ("4", "5"), ("8", "9")]}  # footswitch engaged: 2-1, 5-4, 8-9


def build(xml, cand, sw1=1):
    p = spice.parse(re.sub(r"(\d),(\d)", r"\1.\2", xml))
    gbw, sr, ib, hr = CANDS[cand]
    ov = {r: "skip" for r in "J3 D2 R22 N1 S1 SW1".split()}
    ov["U1"] = f"XU1 {{n3}} {{n2}} {{n7}} {{n4}} {{n6}} OPX params: gbw={gbw} sr={sr} ib={ib} hr={hr}"
    return p, ov


def extra(p, sw1):
    node = spice.node
    net = lambda ref, pin: node(p["parts"][[q["ref"] for q in p["parts"]].index(ref)]["pins"][pin]["net"])
    out = [f"RS1a {net('S1','1')} {net('S1','2')} 0.01", f"RS1b {net('S1','4')} {net('S1','5')} 0.01", f"RS1c {net('S1','8')} {net('S1','9')} 0.01"]
    if sw1:
        out.append(f"RSW1 {net('SW1','2')} {net('SW1','3')} 0.01")
    return out


def ac(xml, cand, st, sw1):
    p, ov = build(xml, cand)
    orig = spice.lines
    spice.lines = lambda *a: orig(*a) + extra(p, sw1)
    old = spice.MODELS
    spice.MODELS = old + OPX
    try:
        return np.array(spice.ac(p, st, ov, {"+VDC": 9.0}, 20, 20000, 40))
    finally:
        spice.lines, spice.MODELS = orig, old


if __name__ == "__main__":
    xml = open(f"{HERE}/mm_v3.xml").read()
    cases = {"mid": dict(RV1=.5, RV2=.5, RV3=1), "RV1 max": dict(RV1=1, RV2=.5, RV3=1), "RV1 min": dict(RV1=0, RV2=.5, RV3=1),
             "RV2 max": dict(RV1=.5, RV2=1, RV3=1), "RV2 min": dict(RV1=.5, RV2=0, RV3=1)}
    for sw1 in (0, 1):
        for cn, st in cases.items():
            ref = ac(xml, "LM4250@5.7uA", st, sw1)
            print(f"== SW1={sw1} {cn}: LM4250 gain @100/1k/5k/10k Hz:", [round(float(np.interp(f, ref[:, 0], ref[:, 1])), 1) for f in (100, 1000, 5000, 10000)])
            for c in list(CANDS)[1:]:
                r = ac(xml, c, st, sw1)
                d = r[:, 1] - ref[:, 1]
                print(f"   {c:14s} diff dB @1k/5k/10k/20k: " + " ".join(f"{float(np.interp(f, r[:, 0], d)):+.1f}" for f in (1000, 5000, 10000, 20000)) + f"   max |d| 20-16k = {np.abs(d[r[:,0] < 16000]).max():.1f}")

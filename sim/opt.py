"""Search: which single DIP-8 op-amps (741 pinout, pins 2 -, 3 +, 6 out, 7 V+, 4 V-) make the Stingray-style preamp pedal V3 respond like the LM4250 at Iset 5.7 uA,
and which part tweak (C6 value; optional socket cap from pin 2 to GND) closes the remaining gap.
Datasheet typicals as remembered (GBW Hz, slew V/us, input bias A, headroom to the rails V at 9 V supply): CHECK them against the datasheet before building."""
import itertools, json, sys
import numpy as np
import mna

import math, os
VS = float(os.environ.get("LM_VS", "9"))
ISET_UA = (VS - 0.5) / 1.5
GBW_REF = float(np.exp(np.interp(np.log(ISET_UA), np.log([1, 2, 5.7, 10, 11.7, 20]), np.log([65e3, 105e3, 200e3, 245e3, 255e3, 290e3]))))
PM = float(np.interp(ISET_UA, [5.7, 11.7], [50, 60]))
F2 = GBW_REF / math.tan(math.radians(90 - PM))
REF = ("LM4250", GBW_REF, 0.022 * ISET_UA ** 0.9)
VMAX = {"TLC271": 16, "OPA333": 5.5, "MCP6061": 6, "OPA391": 5.5, "MCP6041": 6}
# name: (GBW, SR, Ib, headroom, note)
OPAMPS = {
    "TL071": (3e6, 13, 65e-12, 1.5, "JFET"), "TL061": (1e6, 3.5, 30e-12, 1.5, "JFET low power"), "LF441": (1e6, 1.0, 20e-12, 1.5, "JFET low power"),
    "LF351": (4e6, 13, 50e-12, 1.5, "JFET"), "CA3140": (4.5e6, 9, 10e-12, 1.0, "BiMOS"), "OPA134": (8e6, 20, 5e-12, 1.5, "FET audio"),
    "AD820": (1.8e6, 3, 2e-12, 0.05, "FET rail-to-rail"), "MC33171": (1.8e6, 2.1, 20e-9, 1.0, "bipolar low power"),
    "LM741": (1e6, 0.5, 80e-9, 2.0, "bipolar"), "OP07": (0.6e6, 0.3, 2e-9, 2.0, "bipolar precision"), "OP177": (0.6e6, 0.3, 2e-9, 2.0, "bipolar precision"),
    "AD705": (0.8e6, 0.15, 60e-12, 1.5, "bipolar low power"), "OP97": (0.9e6, 0.2, 0.1e-9, 1.5, "bipolar low power"), "LT1006": (0.7e6, 0.2, 12e-9, 1.0, "single supply"),
    "TLC271 high (pin 8 GND)": (1.7e6, 3.6, 1e-12, 0.5, "CMOS programmable"), "TLC271 medium (pin 8 = Vdc)": (0.5e6, 0.43, 1e-12, 0.5, "CMOS programmable"),
    "TLC271 low (pin 8 VDD)": (0.09e6, 0.03, 1e-12, 0.5, "CMOS programmable"),
}
OPAMPS.update({"OPA333 (SOT-23/SO-8, 17uA)": (350e3, 0.16, 70e-12, 0.03, "zero-drift RTR micropower"), "MCP6061 (60uA)": (730e3, 0.3, 1e-12, 0.05, "RTR micropower"),
               "OPA391 (24uA)": (1e6, 0.5, 10e-12, 0.01, "RTR micropower"), "MCP6041 (0.6uA, too slow)": (14e3, 0.0065, 1e-12, 0.05, "nanopower")})
for cc in (47, 68, 100, 150):   # LM308: 1 MHz / 0.3 V/us with 30 pF, both scale with 1/Ccomp (cap between pins 1 and 8, R7 left out)
    OPAMPS[f"LM308 Ccomp {cc}p"] = (1e6 * 30 / cc, 0.3 * 30 / cc, 1.5e-9, 2.0, "needs Ccomp pin1-pin8")

C6S = [0.0, 10e-12, 15e-12, 22e-12, 27e-12, 33e-12, 39e-12, 47e-12, 56e-12, 68e-12, 82e-12, 100e-12, 120e-12, 150e-12, 180e-12, 220e-12, 270e-12, 330e-12]
CPS = [0.0, 4.7e-12, 10e-12, 22e-12, 47e-12]   # extra cap pin 2 -> GND (socket mod)
FR = np.logspace(np.log10(40), np.log10(16000), 36)
CASES = [dict(RV1=a, RV2=b, RV3=1) for a in (0, .25, .5, .75, 1) for b in (0, .5, 1)]


def resp(gbw, c6=120e-12, cp=0.0, f2=None):
    ex = [("C", mna.net("U1", "2"), "GND", cp)] if cp else []
    return np.array([20 * np.log10(np.abs(mna.solve(mna.elements(st, {"C6": c6} if c6 != 120e-12 else None, True, ex), FR, gbw, f2=f2))) for st in CASES])


def err(r, ref):
    d = r - ref
    return float(np.abs(d).max()), float(np.sqrt((d ** 2).mean()))


if __name__ == "__main__":
    ref = resp(REF[1], f2=F2)   # datasheet phase margin (50 deg at 5.7 uA, 60 at 11.7) -> second pole
    res = []
    for name, (gbw, sr, ib, hr, note) in OPAMPS.items():
        if any(name.startswith(k) and VS > v for k, v in VMAX.items()):
            print(f"{name:30s} not usable at {VS:g} V (supply limit)"); continue
        base = err(resp(gbw), ref)
        best = min(((err(resp(gbw, c6, cp), ref), c6, cp) for c6 in C6S for cp in CPS), key=lambda t: t[0][0])
        best_c6 = min(((err(resp(gbw, c6), ref), c6, 0.0) for c6 in C6S), key=lambda t: t[0][0])
        res.append(dict(name=name, gbw=gbw, sr=sr, ib=ib, hr=hr, note=note, base=base, c6=best_c6[1], c6_err=best_c6[0], c6cp=best[1], cp=best[2], cp_err=best[0]))
        print(f"{name:30s} as is {base[0]:5.2f}/{base[1]:4.2f}  C6 {best_c6[1]*1e12:5.0f}p -> {best_c6[0][0]:5.2f}/{best_c6[0][1]:4.2f}   +Cp {best[2]*1e12:4.1f}p C6 {best[1]*1e12:4.0f}p -> {best[0][0]:5.2f}/{best[0][1]:4.2f}", flush=True)
    json.dump(res, open("../data/opt.json", "w"), indent=1)

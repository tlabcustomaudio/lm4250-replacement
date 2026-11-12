"""Low-voltage op-amp on a DIP-8 module: a 5 V LDO whose GND pin sits on a 2.0 V node made by a divider from the pedal's 9 V, so the op-amp
runs between 2.0 V and 7.0 V = 5 V window centred on the pedal's 4.5 V bias (OPA333: 1.8-5.5 V, absolute max 7 V).
usage: LM_VS=9 uv run --with numpy python module.py   (ngspice on PATH)"""
import os, sys
import numpy as np
import emu

RUP, RDN = 78e3, 22e3
MODULE = f"""
.subckt MODULE inp inn vp vn out
Rup vp vm {RUP:g}
Rdn vm vn {RDN:g}
Cvm vm vn 10u
Bldo vreg vm V = min(v(vm)+5, v(vp)-0.25)
Cvr vreg vm 1u
.param imax={0.16e6*1e-3/(6.2832*350e3):.6g}
Ib1 vreg inp DC 70p
Ib2 vreg inn DC 70p
B1 0 n1 I = imax*tanh(1e-3*(v(inp)-v(inn))/imax)
R1 n1 0 1e8
C1 n1 0 {1e-3/(6.2832*350e3):.6g}
Bo n2 0 V = max(min(v(n1), v(vreg)-0.03), v(vm)+0.03)
Ro n2 out 50
Rq vreg vm 300k
.ends
"""
emu.REF += MODULE
if __name__ == "__main__":
    for cn, st in {"mid": dict(RV1=.5, RV2=.5, RV3=1), "RV1 max": dict(RV1=1, RV2=.5, RV3=1)}.items():
        a, b = emu.run_ac("REF", st), emu.run_ac("MODULE", st)
        d = b[:, 1] - a[:, 1]
        print(f"AC {cn}: module - LM4250 ref: max |d| = {np.abs(d).max():.2f} dB")
    # headroom: 1 kHz, output amplitude where it clips (sine amplitude sweep), RV1 mid, volume max
    sr = 192000
    for kind in ("REF", "MODULE"):
        res = []
        for amp in (0.5, 1.0, 1.5, 2.0, 3.0):
            n = int(0.01 * sr)
            x = amp * np.sin(2 * np.pi * 1000 * np.arange(n) / sr)
            y = emu.run_tran(kind, dict(RV1=.5, RV2=.5, RV3=1), x, sr)
            y = y[len(y) // 2:]
            res.append((amp, round(float(np.abs(y - y.mean()).max()), 2)))
        print(kind, "input peak -> output peak (V):", res)

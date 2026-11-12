"""Part-level comparison, independent of the Stingray-style circuit and of R7: for a set of Rset values (-> Iset) and supplies,
GBW / peaking (closed loop x10), follower step slew + overshoot, supply current, for
REF (datasheet curves), CLONE (transistor level, Cc 36 pF), OTA (LM13700-style emulator whose Iabc mirrors Iset) and fixed op-amps.
usage: uv run --with numpy python bench2.py   (ngspice on PATH)"""
import json, math, os, re, subprocess, sys, tempfile
import numpy as np
import clone

CLONE_SUB = clone.SUB.replace("Cc d2 h 30p", "Cc d2 h 36p") + "\n.subckt CLN inp inn vp vn out iset\nXc inn inp vp vn out iset LM4250\n.ends\n"   # same port order as the other models (the clone is (in_n in_p ...))


def ref_curves(iset_ua, vs):
    """datasheet graph readings (+-15 %): GBW Hz, slew V/s, phase margin deg at this Iset and total supply vs (log interpolation between the +-1.5 V and +-15 V lines)."""
    gbw = float(np.exp(np.interp(math.log(iset_ua), np.log([0.1, 0.3, 1, 2, 5.7, 10, 20, 50, 100]), np.log([12e3, 30e3, 62e3, 100e3, 200e3, 245e3, 290e3, 320e3, 320e3]))))
    w = min(max((vs / 2 - 1.5) / 13.5, 0), 1)
    sr_lo, sr_hi = 0.095 * (iset_ua / 5.7) ** 0.91, 0.14 * (iset_ua / 5.7) ** 0.884
    sr = math.exp((1 - w) * math.log(sr_lo) + w * math.log(sr_hi)) * 1e6
    pm_lo = np.interp(math.log(iset_ua), np.log([0.1, 1, 3, 10, 100]), [45, 31, 40, 62, 68])
    pm_hi = np.interp(math.log(iset_ua), np.log([0.1, 1, 3, 10, 100]), [56, 42, 52, 66, 70])
    pm = (1 - w) * pm_lo + w * pm_hi
    return gbw, sr, float(pm)


def ref_sub(gbw, sr, pm):
    f2 = gbw / math.tan(math.radians(90 - pm))
    return f"""
.subckt REF inp inn vp vn out iset
.param imax={sr*1e-3/(6.2832*gbw):.6g}
Ib1 vp inp DC 15n
Ib2 vp inn DC 15n
B1 0 n1 I = imax*tanh(1e-3*(v(inp)-v(inn))/imax)
R1 n1 0 1e8
C1 n1 0 {1e-3/(6.2832*gbw):.6g}
Bo n2 0 V = max(min(v(n1), v(vp)-0.3), v(vn)+0.3)
R2p n2 n3 1k
C2p n3 0 {1/(6.2832*f2*1e3):.6g}
Ro n3 out 50
.ends
"""


def fixed_sub(gbw, sr, hr):
    return f"""
.subckt FIX inp inn vp vn out iset
.param imax={sr*1e-3/(6.2832*gbw):.6g}
B1 0 n1 I = imax*tanh(1e-3*(v(inp)-v(inn))/imax)
R1 n1 0 1e8
C1 n1 0 {1e-3/(6.2832*gbw):.6g}
Bo n2 0 V = max(min(v(n1), v(vp)-{hr}), v(vn)+{hr})
Ro n2 out 50
.ends
"""


VT2 = 0.0517
# OTA emulator: input buffers + differential divider a, OTA current Iabc = K * Iset (mirror of pin 8), inverting integrator C, leak 200M
OTA_A, OTA_K, OTA_C = 0.618, 3.5, 191e-12
RS = 12e3
RD = OTA_A * 2 * RS / (1 - OTA_A)
OTA = f"""
.model DQ D(IS=2e-14 N=1)
.subckt OTA inp inn vp vn out iset
Eb1 bp 0 inp 0 1
Eb2 bn 0 inn 0 1
Rs1 bp dp {RS:g}
Rs2 bn dn {RS:g}
Rd dp dn {RD:g}
Ib1 vp inp DC 15n
Ib2 vp inn DC 15n
Dq vp m DQ
Vs0 m iset 0
Rr1 vp ref 100k
Rr2 ref vn 100k
Cr ref vn 100n
Bota s ref I = {OTA_K}*i(Vs0)*tanh((v(dp)-v(dn))/{VT2})
Cint out s {OTA_C:.4g}
Rleak out s 200Meg
Gop 0 n1 ref s 1
Rop n1 0 1e5
Cop n1 0 {1/(6.2832*20e6*1e5):.6g}
Bo n2 0 V = max(min(v(n1), v(vp)-0.1), v(vn)+0.1)
Ro n2 out 20
.ends
"""


def run(deck, files):
    with tempfile.TemporaryDirectory() as d:
        open(d + "/c.cir", "w").write(deck.replace("@D@", d))
        r = subprocess.run(["ngspice", "-b", d + "/c.cir"], capture_output=True, text=True, timeout=300)
        out = {}
        for f in files:
            p = f"{d}/{f}.txt"
            out[f] = [[float(x) for x in l.split()] for l in open(p)] if os.path.isfile(p) and os.path.getsize(p) else None
        out["log"] = r.stdout[-600:]
        return out


def deck_common(sub, name, vs, iset_ua, body, ctl):
    rset = (vs - 0.5) / (iset_ua * 1e-6)
    return f"""* bench
{sub}
VP vp 0 {vs}
VM ref 0 {vs/2}
Rset iset 0 {rset:g}
{body}
.control
{ctl}
.endc
.end
"""


def measure(sub, name, vs, iset_ua):
    # (a) closed loop gain 10, non-inverting around mid-supply: bandwidth + peaking
    body = f"""VI sig ref DC 0 AC 1
X1 sig inm vp 0 out iset {name}
Rf out inm 9k
Rg inm ref 1k
RL out 0 100k
CL out 0 20p
Vsup vp 0 {vs}"""
    body = body.replace("Vsup vp 0 %s" % vs, "")
    ac = run(deck_common(sub, name, vs, iset_ua, body, "ac dec 40 100 3Meg\nwrdata @D@/ac.txt vdb(out)"), ["ac"])["ac"]
    f = np.array([r[0] for r in ac]); g = np.array([r[1] for r in ac])
    g0 = g[:8].mean()
    f3 = float(np.interp(-3, -(g - g0)[np.argmax(g):][::-1] * -1, f[np.argmax(g):][::-1])) if False else None
    below = np.where(g < g0 - 3)[0]
    f3 = float(f[below[0]]) if len(below) else float("nan")
    peak = float(g.max() - g0)
    # (b) follower step 1 V p-p: slew (20-80 %) and overshoot
    body = f"""VI sig 0 PULSE({vs/2-0.5} {vs/2+0.5} 50u 100n 100n 600u 1.4m)
X1 sig out vp 0 out iset {name}
RL out 0 100k
CL out 0 20p"""
    tr = run(deck_common(sub, name, vs, iset_ua, body, "tran 0.1u 200u\nwrdata @D@/tr.txt v(out)"), ["tr"])["tr"]
    t = np.array([r[0] for r in tr]); v = np.array([r[1] for r in tr])
    lo, hi = v[t < 50e-6].mean(), v[(t > 150e-6)].mean()
    mid = (t > 51e-6) & (v > lo + 0.3 * (hi - lo)) & (v < lo + 0.7 * (hi - lo))      # slope of the middle 40 % of the step (feed-through spikes ignored)
    sr = float(np.polyfit(t[mid], v[mid], 1)[0] / 1e6) if mid.sum() > 4 else float("nan")
    over = float((v[t > 50e-6].max() - hi) / (hi - lo) * 100)
    # (c) supply current at rest
    body = f"""VI sig ref DC 0
X1 sig out vp 0 out iset {name}
RL out 0 100k"""
    op = run(deck_common(sub, name, vs, iset_ua, body, "op\nwrite @D@/op.raw\nprint i(VP)"), [])["log"]
    m = re.search(r"i\(vp\)\s*=\s*([-\d.e+]+)", op)
    iq = abs(float(m.group(1))) * 1e6 if m else float("nan")
    return dict(f3_x10=f3 * 10 / 1e3, peak_db=peak, slew=sr, overshoot=over, iq_ua=iq)


if __name__ == "__main__":
    ISETS = [1, 2, 3, 5.7, 10, 20]
    FIXED = {"TL071": (3e6, 13e6, 1.5), "TL061": (1e6, 3.5e6, 1.5), "OP07": (0.6e6, 0.3e6, 2.0), "LM308+100p": (0.3e6, 0.09e6, 2.0), "OPA333": (350e3, 0.16e6, 0.03)}
    res = {}
    for vs in ((9.0, 18.0) if "18" not in sys.argv[1:2] else (18.0,)):
        for iset in ISETS:
            gbw, sr, pm = ref_curves(iset, vs)
            row = {"REF": measure(ref_sub(gbw, sr, pm), "REF", vs, iset), "CLONE": measure(CLONE_SUB, "CLN", vs, iset)}
            row["REF"]["gbw_graph"] = gbw / 1e3; row["REF"]["sr_graph"] = sr / 1e6; row["REF"]["pm"] = pm
            for k, (g, s, h) in FIXED.items():
                if k == "OPA333" and vs > 5.5:
                    continue
                row[k] = measure(fixed_sub(g, s, h), "FIX", vs, iset)
            res[f"{vs:g}V_{iset}uA"] = row
            print(f"VS={vs:g} Iset={iset:5.1f}uA  ref GBW {gbw/1e3:5.0f}k SR {sr/1e6:.3f} PM {pm:3.0f} | " + " | ".join(f"{k}: BW10 {m['f3_x10']:6.0f}k pk {m['peak_db']:4.1f} SR {m['slew']:.3f} ov {m['overshoot']:4.1f}% Iq {m['iq_ua']:.0f}" for k, m in row.items() if k in ("REF", "CLONE")), flush=True)
            json.dump(res, open("../data/bench2.json", "w"), indent=1)

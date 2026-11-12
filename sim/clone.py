"""Transistor-level clone of the LM4250 from AN-71 fig. 1 (generic BJT models), checked against the datasheet curves at Iset ~ 5.7 uA, VS = 9 V.
usage: clone.py   (needs ngspice on PATH)"""
import os, re, subprocess, sys, tempfile

SUB = """
.model QN NPN(IS=1e-14 BF=200 VAF=100 RB=100 CJE=1p CJC=0.5p TF=0.5n)
.model QPL PNP(IS=5e-15 BF=150 VAF=50 RB=150 CJE=2p CJC=1p TF=20n)
.model QPS PNP(IS=5e-15 BF=40 VAF=50 RB=150 CJE=2p CJC=1p TF=20n)
.subckt LM4250 in_n in_p vp vn out iset
R8 vp a 100
R9 a e9 5k
Q9 iset iset e9 QPL
R10 a e10 6k
Q10 tail iset e10 QPL
R11 a e11 5k
Q11 e iset e11 QPL
R12 vp e12 2.5k
Q12 s12 iset e12 QPL
R1 tail e1 10k
R2 tail e2 10k
Q1 d1 in_n e1 QPL
Q2 d2 in_p e2 QPL
Q3 d1 d1 n5 QN
R3 n5 vn 5k
Q4 d2 d1 n1 QN
R4 n1 vn 5k
Q5 vn d2 e QPL
Q6 e e g QN
Q7 g d1 e7 QN
R7 e7 vn 10k
Q8 h g vn QN
Cc d2 h 30p
Q13 s12 s12 m QN
Q14 m m h QN
Q15 a s12 x1 QN
R16 x1 x2 50
R15 x2 o1 100
Q18 vn h x4 QPS
R17 x4 x3 100
R14 x3 o1 50
R13 o1 out 100
.ends
"""


def run(deck, vars_):
    with tempfile.TemporaryDirectory() as d:
        open(d + "/c.cir", "w").write(deck.replace("@D@", d))
        r = subprocess.run(["ngspice", "-b", d + "/c.cir"], capture_output=True, text=True, timeout=300)
        out = {}
        for v in vars_:
            p = f"{d}/{v}.txt"
            out[v] = [[float(x) for x in l.split()] for l in open(p)] if os.path.isfile(p) else None
        return out, r.stdout[-1500:]


def bench(iset=5.7e-6, vs=9.0):
    rset = (vs - 0.5) / iset
    # follower, +/-1 V step around mid supply, for slew; closed loop gain 100 (inverting) for GBW; DC: Iq, Vos
    deck = f"""* clone
{SUB}
VP vp 0 {vs}
VR ref 0 {vs/2}
Rset iset 0 {rset:g}
* (a) DC: unity follower at mid supply
Xa vp_ ref_ 0 0 0 0 LM4250
.end
"""
    return deck


def run_op(iset=5.7e-6, vs=9.0):
    rset = (vs - 0.5) / iset
    deck = f"""* op
{SUB}
VP vp 0 {vs}
VR inp 0 {vs/2}
Rset iset 0 {rset:g}
X1 out inp vp 0 out iset LM4250
RL out 0 100k
.control
op
print v(out) i(vp) v(x1.d1) v(x1.d2) v(x1.h) v(x1.s12) v(x1.tail) v(x1.e) v(x1.g)
.endc
.end
"""
    with tempfile.TemporaryDirectory() as d:
        open(d + "/c.cir", "w").write(deck)
        r = subprocess.run(["ngspice", "-b", d + "/c.cir"], capture_output=True, text=True, timeout=120)
        return r.stdout[-1800:] + r.stderr[-500:]


if __name__ == "__main__":
    print(run_op())


def measure(iset=5.7e-6, vs=9.0, extra=""):
    rset = (vs - 0.5) / iset
    deck = f"""* bench
{SUB}
{extra}
VP vp 0 {vs}
VM ref 0 {vs/2}
Rset iset 0 {rset:g}
* closed loop gain 21, AC
VI inp ref DC 0 AC 1
X1 out inm vp 0 out_ iset LM4250
.end
"""
    return deck


def bench_ac(iset, vs=9.0, gain=21, ex=""):
    rset = (vs - 0.5) / iset
    deck = f"""* ac
{SUB}
{ex}
VP vp 0 {vs}
VM ref 0 {vs/2}
Rset iset 0 {rset:g}
VI sig ref DC 0 AC 1
Rb ref2 0 1e-9
X1 inm sig vp 0 out iset LM4250
Rf out inm {(gain-1)*1e3:g}
Rg inm ref 1k
RL out 0 100k
CL out 0 20p
.control
ac dec 40 100 3Meg
meas ac f3db WHEN vdb(out)=vdb(out)-3 
wrdata @D@/ac.txt vdb(out)
.endc
.end
"""
    return deck


def bench_tran(iset, vs=9.0, step=1.0, ex=""):
    rset = (vs - 0.5) / iset
    deck = f"""* tran follower
{SUB}
{ex}
VP vp 0 {vs}
Rset iset 0 {rset:g}
VI sig 0 PULSE({vs/2-step/2} {vs/2+step/2} 20u 100n 100n 400u 800u)
X1 out sig vp 0 out iset LM4250
RL out 0 100k
CL out 0 20p
.control
tran 0.5u 800u
wrdata @D@/tr.txt v(out) v(sig)
.endc
.end
"""
    return deck


def analyse(iset=5.7e-6, vs=9.0):
    import math
    ac, _ = run(bench_ac(iset, vs), ["ac"])
    a = ac["ac"]
    f = [r[0] for r in a]; g = [r[1] for r in a]
    g0 = max(g[:10])
    f3 = next((f[i] for i in range(len(f)) if g[i] < g0 - 3), None)
    tr, _ = run(bench_tran(iset, vs), ["tr"])
    t = [r[0] for r in tr["tr"]]; v = [r[1] for r in tr["tr"]]
    lo, hi = min(v[i] for i in range(len(v)) if t[i] < 20e-6), max(v[i] for i in range(len(v)) if t[i] < 300e-6)
    t20 = next(t[i] for i in range(len(v)) if t[i] > 20e-6 and v[i] > lo + 0.2 * (hi - lo))
    t80 = next(t[i] for i in range(len(v)) if t[i] > 20e-6 and v[i] > lo + 0.8 * (hi - lo))
    sr = 0.6 * (hi - lo) / (t80 - t20) / 1e6   # 20-80 % of the step
    return f3 and f3 * 21, sr


if __name__ == "__main__" and "bench" in sys.argv:
    for iset in (1e-6, 2e-6, 5.7e-6, 10e-6):
        gbw, sr = analyse(iset)
        print(f"Iset {iset*1e6:4.1f} uA: GBW ~ {gbw/1e3 if gbw else 0:6.0f} kHz   slew {sr:.3f} V/us")

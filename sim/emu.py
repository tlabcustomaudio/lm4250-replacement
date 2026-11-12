"""LM4250 emulator (behavioural ngspice model of the proposed circuit) vs the datasheet-fitted reference, inside the Stingray-style Stomp.
Reference (LM4250 @ Iset 5.7 uA, VS = 9 V, datasheet curves): GBW 200 kHz, slew 0.11 V/us, Ib ~15 nA, Rin 8.5 Mohm, A0 1e5.
Emulator: input buffers -> differential divider a -> OTA (LM13700: Iout = Iabc tanh(Vd/2VT), gm = 19.2*Iabc) -> inverting integrator (rail-to-rail op-amp, C)."""
import os, re, sys, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, spice
import study

VS = float(os.environ.get("LM_VS", "9"))        # supply voltage; R7 stays 1M5 -> Iset = (VS - 0.5) / 1.5M
ISET_UA = (VS - 0.5) / 1.5
GBW = float(np.exp(np.interp(np.log(ISET_UA), np.log([1, 2, 5.7, 10, 11.7, 20]), np.log([65e3, 105e3, 200e3, 245e3, 255e3, 290e3]))))   # datasheet graph, +-15 %
SR = 0.022 * ISET_UA ** 0.9 * 1e6                # V/s, datasheet graph (0.11 V/us at 5.7 uA)
PM = float(np.interp(ISET_UA, [5.7, 11.7], [50, 60]))      # phase margin graph
F2 = GBW / math.tan(math.radians(90 - PM))        # second pole
VL = SR / (2 * math.pi * GBW)    # linear range of the reference input stage, V (0.0875)
VT2 = 2 * 0.02585                # OTA: Iout = Iabc*tanh(Vd / 2VT)
A = VT2 / VL                     # differential attenuation in front of the OTA (~0.59)
IABC = 20e-6
C = IABC / SR                    # integrator cap: SR = Iabc / C  -> 182 pF
print(f"VS={VS:g} V Iset={ISET_UA:.1f} uA GBW={GBW/1e3:.0f} kHz SR={SR/1e6:.3f} V/us PM={PM:.0f} f2={F2/1e3:.0f} kHz  VL={VL*1e3:.1f} mV  a={A:.3f}  Iabc={IABC*1e6:.0f} uA  C={C*1e12:.0f} pF  gbw check={(19.2*IABC*A)/(2*math.pi*C)/1e3:.0f} kHz")

EMU = f"""
.subckt EMU inp inn vp vn out params: iabc={IABC} cint={C} rs=12k rd={{rs*2*(1/{A}-1)/2/(1-1) if 0 else 1}}
.ends
"""
# plain text version (no param arithmetic tricks)
RS = 12e3
RD = A * 2 * RS / (1 - A)        # Rd/(Rd+2Rs) = a
EMU = f"""
.subckt EMU inp inn vp vn out
Eb1 bp 0 inp 0 1
Eb2 bn 0 inn 0 1
Rs1 bp dp {RS:g}
Rs2 bn dn {RS:g}
Rd dp dn {RD:g}
Rin inp inn 8.5Meg
Ib1 vp inp DC 15n
Ib2 vp inn DC 15n
* reference level for the integrator = mid supply
Rr1 vp ref 100k
Rr2 ref vn 100k
Cr ref vn 100n
* OTA: current into the summing node s (sign: inverting integrator, so '+' input drives the output up)
Bota s ref I = {IABC:g}*tanh((v(dp)-v(dn))/{VT2:.5f})
Cint out s {C:.4g}
Rleak out s 200Meg
* rail-to-rail integrator op-amp: ideal, 100 dB, 20 MHz, swing to 0.1 V of the rails
Gop 0 n1 ref s 1
Rop n1 0 1e5
Cop n1 0 {{1/(6.2832*20Meg*1e5)}}
Bo n2 0 V = max(min(v(n1), v(vp)-0.1), v(vn)+0.1)
Ro n2 out 20
.ends
"""
REF = f"""
.subckt REF inp inn vp vn out
.param imax={SR*1e-3/(6.2832*GBW)}
Rin inp inn 8.5Meg
Ib1 vp inp DC 15n
Ib2 vp inn DC 15n
B1 0 n1 I = imax*tanh(1e-3*(v(inp)-v(inn))/imax)
R1 n1 0 1e8
C1 n1 0 {{1e-3/(6.2832*{GBW})}}
Bo n2 0 V = max(min(v(n1), v(vp)-0.3), v(vn)+0.3)
* second pole: datasheet phase margin ~50 deg at Iset 5.7 uA -> f2 = fu / tan(40 deg) = 238 kHz
R2p n2 n3 1k
C2p n3 0 {{1/(6.2832*{F2}*1k)}}
Ro n3 out 50
.ends
"""


import clone as _clone  # noqa
CLONE = _clone.SUB.replace("Cc d2 h 30p", "Cc d2 h 36p")


def deck(kind, st, analysis_ac=True):
    xml = open(study.HERE + "/mm_v3.xml").read()
    p = spice.parse(re.sub(r"(\d),(\d)", r"\1.\2", xml))
    ov = {r: "skip" for r in "J3 D2 R22 N1 S1 SW1".split()}
    ov["U1"] = (f"XU1 {{n2}} {{n3}} {{n7}} {{n4}} {{n6}} {{n8}} LM4250" if kind == "CLONE" else f"XU1 {{n3}} {{n2}} {{n7}} {{n4}} {{n6}} {kind}")
    orig = spice.lines
    spice.lines = lambda *a: orig(*a) + study.extra(p, 1)
    old = spice.MODELS
    spice.MODELS = old + EMU + REF + (CLONE if kind == 'CLONE' else '')
    return p, ov, orig, old


def run_ac(kind, st):
    p, ov, orig, old = deck(kind, st)
    try:
        return np.array(spice.ac(p, st, ov, {"+VDC": VS}, 20, 20000, 30))
    finally:
        spice.lines, spice.MODELS = orig, old


def run_tran(kind, st, x, sr):
    p, ov, orig, old = deck(kind, st)
    try:
        return np.array(spice.tran(p, list(x), sr, settings=st, overrides=ov, supplies={"+VDC": VS}, rs=1e3))
    finally:
        spice.lines, spice.MODELS = orig, old


if __name__ == "__main__" and sys.argv[1:2] != ["tran"]:
    for cn, st in {"mid": dict(RV1=.5, RV2=.5, RV3=1), "RV1 max": dict(RV1=1, RV2=.5, RV3=1), "RV1 min": dict(RV1=0, RV2=.5, RV3=1), "RV2 max": dict(RV1=.5, RV2=1, RV3=1)}.items():
        a, b = run_ac("REF", st), run_ac(sys.argv[1] if len(sys.argv) > 1 else "EMU", st)
        d = b[:, 1] - a[:, 1]
        print(f"AC {cn:8s} ref @1k/5k/10k/20k: " + " ".join(f"{float(np.interp(f, a[:,0], a[:,1])):+.1f}" for f in (1000, 5000, 10000, 20000)) + f"   emu - ref: max |d| = {np.abs(d).max():.2f} dB")


def tran_test():
    """10 kHz / 5 kHz bursts at RV1 max (treble boost +24 dB): slew-limited outputs of reference vs emulator."""
    sr = 960000
    out = {}
    for f, amp in ((10000, 0.12), (10000, 0.3), (5000, 0.5), (2000, 1.0)):
        n = int(0.004 * sr)
        x = amp * np.sin(2 * np.pi * f * np.arange(n) / sr) * np.minimum(1, np.arange(n) / (0.0005 * sr))
        st = dict(RV1=1, RV2=.5, RV3=1)
        a, b = run_tran("REF", st, x, sr), run_tran(sys.argv[2] if len(sys.argv) > 2 else "EMU", st, x, sr)
        m = slice(len(a) // 2, None)
        a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
        k = min(len(a), len(b))
        a, b = a[:k], b[:k]
        thd = lambda y: 20 * np.log10(np.linalg.norm(y - np.dot(y, np.sin(2*np.pi*f*np.arange(len(y))/sr))*np.sin(2*np.pi*f*np.arange(len(y))/sr)/np.dot(np.sin(2*np.pi*f*np.arange(len(y))/sr), np.sin(2*np.pi*f*np.arange(len(y))/sr)) - np.dot(y, np.cos(2*np.pi*f*np.arange(len(y))/sr))*np.cos(2*np.pi*f*np.arange(len(y))/sr)/np.dot(np.cos(2*np.pi*f*np.arange(len(y))/sr), np.cos(2*np.pi*f*np.arange(len(y))/sr))) / np.linalg.norm(y) + 1e-12)
        print(f"{f} Hz in {amp} V: out peak ref {np.abs(a).max():.2f} V emu {np.abs(b).max():.2f} V; waveform diff rms {np.sqrt(np.mean((a-b)**2)):.4f} V ({20*np.log10(np.sqrt(np.mean((a-b)**2))/np.sqrt(np.mean(a**2))+1e-12):.1f} dB re ref); distortion ref {thd(a):.1f} dB emu {thd(b):.1f} dB", flush=True)

if __name__ == "__main__" and "tran" in sys.argv[1:2]:
    tran_test()

"""Find the value of one part (default C6) that makes a TL071 / TLC271 circuit match the LM4250 response in every knob case."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, spice, study

xml = open(study.HERE + "/mm_v3.xml").read()
CASES = [dict(RV1=a, RV2=b, RV3=1) for a in (0, .5, 1) for b in (0, .5, 1)]


def curves(cand, part=None, val=None):
    out = []
    for st in CASES:
        p, ov = study.build(xml, cand)
        if part:
            ov[part] = val
        orig = spice.lines
        spice.lines = lambda *a: orig(*a) + study.extra(p, 1)
        old = spice.MODELS; spice.MODELS = old + study.OPX
        try:
            out.append(np.array(spice.ac(p, st, ov, {"+VDC": 9.0}, 20, 20000, 30)))
        finally:
            spice.lines, spice.MODELS = orig, old
    return out


if __name__ == "__main__":
    ref = curves("LM4250@5.7uA")
    for cand, part in (("TL071", "C6"), ("TLC271 medium", "C6")):
        best = []
        for v in ("0.1p", "22p", "33p", "47p", "68p", "82p", "100p"):
            cs = curves(cand, part, v)
            err = max(float(np.abs(c[:, 1] - r[:, 1])[c[:, 0] < 16000].max()) for c, r in zip(cs, ref))
            best.append((err, v)); print(cand, part, v, f"worst |d| 20-16k = {err:.2f} dB", flush=True)

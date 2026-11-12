"""Fast linear AC solver for the Stingray-style Stomp netlist (R, C, pots, joined switch contacts, one-pole op-amp U1).
Used for the op-amp search; validated against ngspice (study.py)."""
import os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import spice

XML = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mm_v3.xml")).read()
P = spice.parse(re.sub(r"(\d),(\d)", r"\1.\2", XML))
PART = {p["ref"]: p for p in P["parts"]}
net = lambda ref, pin: PART[ref]["pins"][pin]["net"]
GND = {"GND"}
JOIN = [("S1", "1", "2"), ("S1", "4", "5"), ("S1", "8", "9")]   # footswitch engaged


def elements(st, vals=None, sw1=True, extra=()):
    """list of (kind, n1, n2, value). vals overrides {ref: ohms/farads}."""
    vals = vals or {}
    el = []
    for ref, p in PART.items():
        k = p["kind"]
        if k in ("resistor", "capacitor") and p["pins"]:
            n = [p["pins"][x]["net"] for x in sorted(p["pins"])]
            v = vals.get(ref, spice.num(p["value"]))
            el.append(("R" if k == "resistor" else "C", n[0], n[1], v))
        elif k == "pot":
            ohms, t = spice.pot(p["value"])
            ohms = vals.get(ref, ohms)
            f = spice.taper(t, st.get(ref, 0.5))
            nn = {x: p["pins"][x]["net"] for x in p["pins"]}
            el.append(("R", nn["1"], nn["2"], max(ohms * f, 1)))
            el.append(("R", nn["2"], nn["3"], max(ohms * (1 - f), 1)))
    for r, a, b in JOIN:
        el.append(("R", net(r, a), net(r, b), 0.01))
    if sw1:
        el.append(("R", net("SW1", "2"), net("SW1", "3"), 0.01))
    return el + list(extra)


def solve(el, freqs, gbw, a0=1e5, ibias=0.0, f2=None):
    """transfer function IN -> OUT (complex) for U1 = one-pole op-amp with unity-gain frequency gbw (Hz)."""
    names = sorted({n for e in el for n in e[1:3] if n not in GND and n != "+VDC"} | {net("U1", "6"), "IN", "OUT", net("U1", "3"), net("U1", "2")})
    ix = {n: i for i, n in enumerate(names)}
    N = len(names)
    out = []
    wp = 2 * np.pi * gbw / a0
    for f in freqs:
        s = 1j * 2 * np.pi * f
        M = np.zeros((N + 2, N + 2), complex)
        rhs = np.zeros(N + 2, complex)
        idx = lambda n: ix.get(n)
        for kind, a, b, v in el:
            y = 1 / v if kind == "R" else s * v
            ia, ib = idx(a), idx(b)
            if ia is not None: M[ia, ia] += y
            if ib is not None: M[ib, ib] += y
            if ia is not None and ib is not None: M[ia, ib] -= y; M[ib, ia] -= y
        for n in names:
            M[ix[n], ix[n]] += 1e-12
        i_in = ix["IN"]; M[N, i_in] = 1; M[i_in, N] += 1; rhs[N] = 1          # Vin = 1
        o, p_, m_ = ix[net("U1", "6")], ix[net("U1", "3")], ix[net("U1", "2")]
        A = a0 / (1 + s / wp) / (1 + s / (2 * np.pi * f2) if f2 else 1)
        M[N + 1, o] = 1; M[N + 1, p_] = -A; M[N + 1, m_] = A; M[o, N + 1] += 1  # Vout = A (V+ - V-), ideal source
        out.append(np.linalg.solve(M, rhs)[ix["OUT"]])
    return np.array(out)


if __name__ == "__main__":
    fr = [100, 1000, 5000, 10000]
    for name, st in (("mid", dict(RV1=.5, RV2=.5, RV3=1)), ("RV1 max", dict(RV1=1, RV2=.5, RV3=1)), ("RV1 min", dict(RV1=0, RV2=.5, RV3=1))):
        h = solve(elements(st), fr, 200e3)
        print(name, [round(float(20 * np.log10(abs(x))), 1) for x in h])

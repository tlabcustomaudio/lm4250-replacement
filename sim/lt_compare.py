"""Same netlists as compare_all.py, run in LTspice (Mac) with .meas at fixed frequencies, compared with ngspice.
usage: uv run --with numpy python lt_compare.py [test|run]"""
import os, re, subprocess, sys
import numpy as np
import compare_all as ca, spice, study, emu

LT = "/Applications/LTspice.app/Contents/MacOS/LTspice"
FREQS = [100, 300, 1000, 3000, 5000, 8000, 10000, 12000, 16000, 20000]
DIR = "lm4250-lt"


def lt_deck(name, st):
    p, ov, orig, old = ca.build(name)
    try:
        text, o = spice.deck(p, st, ov, {"+VDC": ca.VS}, "DC 0 AC 1", "")
    finally:
        spice.lines, spice.MODELS = orig, old
    text = re.sub(r"\.control.*?\.endc", "", text, flags=re.S)
    text = re.sub(r"\.options[^\n]*", ".options plotwinsize=0", text)
    meas = "\n".join(f".meas ac g{f} find mag(v({o})) at {f}" for f in FREQS)
    i = text.rstrip().rfind("\n.end")
    return text[:i] + f"\n.ac dec 40 20 25k\n{meas}\n.end\n"


def batch(decks):
    os.makedirs("lt", exist_ok=True)
    for t, d in decks.items():
        open(f"lt/{t}.cir", "w").write(d)
    subprocess.run(f"ssh mac 'rm -rf {DIR}; mkdir -p {DIR}' && scp -q lt/*.cir mac:{DIR}/", shell=True, check=True)
    out = {}
    tags = list(decks)
    for i in range(0, len(tags), 10):
        grp = tags[i:i + 10]
        sh = f"cd {DIR} && for f in " + " ".join(f"{t}.cir" for t in grp) + f"; do {LT} -b $f & done; wait; for f in " + " ".join(f"{t}.log" for t in grp) + "; do echo \"=== $f\"; iconv -f UTF-16LE -t UTF-8 $f 2>/dev/null || cat $f; done"
        res = subprocess.run(["ssh", "mac", sh], capture_output=True, text=True).stdout
        for m in re.finditer(r"=== (\S+)\.log\n(.*?)(?=\n=== |\Z)", res, re.S):
            out[m.group(1)] = m.group(2)
    return out


def parse(log):
    g = {}
    for f in FREQS:
        m = re.search(rf"^g{f}:.*?=\(([-\d.eE+]+)dB", log, re.M)
        g[f] = float(m.group(1)) if m else float("nan")
    return g


if __name__ == "__main__":
    st = dict(RV1=1, RV2=.5, RV3=1)
    if sys.argv[1:2] == ["test"]:
        logs = batch({"ref": lt_deck("LM4250 reference (2 poles)", st)})
        print(logs.get("ref", "")[-1500:])

    if sys.argv[1:2] == ["run"]:
        import json
        names = list(ca.CANDS)
        decks = {f"{i}_{j}": lt_deck(n, st) for i, n in enumerate(names) for j, st in enumerate(ca.CASES)}
        logs = batch(decks)
        res = {}
        for i, n in enumerate(names):
            lt = np.array([[parse(logs.get(f"{i}_{j}", ""))[f] for f in FREQS] for j in range(len(ca.CASES))])
            ng = np.array([[float(np.interp(f, a[:, 0], a[:, 1])) for f in FREQS] for a in [ca.ac(n, st) for st in ca.CASES]])
            res[n] = (lt, ng)
            print(f"{n:34s} LTspice vs ngspice: max |d| = {np.nanmax(np.abs(lt - ng)):.3f} dB", flush=True)
        ref_lt = res[names[0]][0]
        rows = {}
        for n in names[1:]:
            d = res[n][0] - ref_lt
            mid = [k for k, f in enumerate(FREQS) if f <= 16000]
            rows[n] = dict(ac_w_lt=float(np.nanmax(np.abs(d[:, mid]))), ac_hi_lt=float(np.nanmax(np.abs(d[:, [k for k, f in enumerate(FREQS) if f > 16000]]))))
            print(f"{n:34s} LTspice worst dB 100 Hz-16 kHz {rows[n]['ac_w_lt']:.2f}   at 20 kHz {rows[n]['ac_hi_lt']:.2f}")
        json.dump(rows, open("../data/lt_compare.json", "w"), indent=1)


def lt_tran_deck(name, f, amp):
    st = dict(RV1=1, RV2=.5, RV3=1)
    p, ov, orig, old = ca.build(name)
    try:
        text, o = spice.deck(p, st, ov, {"+VDC": ca.VS}, f"SINE(0 {amp} {f})", "")
    finally:
        spice.lines, spice.MODELS = orig, old
    text = re.sub(r"\.control.*?\.endc", "", text, flags=re.S)
    text = re.sub(r"\.options[^\n]*", ".options plotwinsize=0", text)
    text = text.replace("VIN IN 0 SINE", "VIN sig 0 SINE").replace("RLOAD ", "Rsrc sig IN 1k\nRLOAD ", 1)
    i = text.rstrip().rfind("\n.end")
    return text[:i] + f"\n.tran 0 6m 0 0.5u\n.four {f} 12 v({o})\n.end\n"


def parse_four(log):
    h1 = re.search(r"^\s*1\s+[\d.eE+-]+\s+([\d.eE+-]+)", log, re.M)
    thd = re.search(r"Total Harmonic Distortion:\s*([\d.eE+-]+)%", log)
    if not (h1 and thd):
        return float("nan"), float("nan")
    return 20 * np.log10(float(h1.group(1))), 20 * np.log10(float(thd.group(1)) / 100)


if __name__ == "__main__" and sys.argv[1:2] == ["tran"]:
    import json
    names = list(ca.CANDS); bursts = ca.BURSTS[:3]
    logs = batch({f"{i}_{k}": lt_tran_deck(n, f, a) for i, n in enumerate(names) for k, (f, a) in enumerate(bursts)})
    ref = None
    out = {}
    for i, n in enumerate(names):
        out[n] = [parse_four(logs.get(f"{i}_{k}", "")) for k in range(len(bursts))]
    ng = json.load(open("../data/compare_all.json"))
    for n in names:
        if n.startswith("LM4250 ref"):
            print(f"{n:34s} LT (level dB, THD dB) {[tuple(round(v, 1) for v in t) for t in out[n]]}   ngspice {[tuple(t) for t in ng['ref_tr'][:3]]}")
        else:
            print(f"{n:34s} LT {[tuple(round(v, 1) for v in t) for t in out[n]]}   ngspice {ng['rows'][n]['tr'][:3]}")

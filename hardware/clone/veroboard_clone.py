"""Stripboard layout of the discrete LM4250 clone, generated and verified automatically.
Idea: every strip (row) carries ONE net; each TO-92 sits across three adjacent strips (C, B, E) so most transistors need no wire at all; resistors stand
vertically between two strips 3-6 holes apart; a net needing a second strip gets a jumper wire. No tracks are cut.
   uv run --with matplotlib python veroboard_clone.py [seed] [seconds]"""
import random, re, sys, time
sys.path.insert(0, "../../sim")
import clone

RENAME = {"vp": "+9V", "vn": "GND", "in_n": "IN-", "in_p": "IN+", "out": "OUT", "iset": "ISET", "a": "A", "tail": "TAIL", "d1": "D1", "d2": "D2", "e": "E", "g": "G", "h": "H",
          "s12": "S12", "m": "M", "n5": "NULL5", "n1": "NULL1", "o1": "O1", "x1": "X1", "x2": "X2", "x3": "X3", "x4": "X4"}
net = lambda n: RENAME.get(n, n)
TRS, RES, CAPS = [], [], []
for ln in clone.SUB.replace("Cc d2 h 30p", "Cc d2 h 39p").splitlines():
    t = ln.split()
    if not t or t[0].startswith((".", "*")): continue
    ref = t[0] if t[0] == "Cc" else t[0][0] + str(int(t[0][1:]) + 100)
    if t[0][0] == "Q": TRS.append((ref, "NPN" if t[4] == "QN" else "PNP", net(t[1]), net(t[2]), net(t[3])))
    elif t[0][0] == "R": RES.append((ref, net(t[1]), net(t[2]), t[3]))
    elif t[0] == "Cc": CAPS.append(("C101", net(t[1]), net(t[2]), "39p"))
TWO = [(r, a, b, v) for r, a, b, v in RES] + CAPS           # two-lead parts that stand between strips
VALUE = {"R101": "10k", "R102": "10k", "R103": "4.99k", "R104": "4.99k", "R107": "10k", "R108": "100R", "R109": "4.99k", "R110": "6.04k", "R111": "4.99k", "R112": "2.49k",
         "R113": "100R", "R114": "49.9R", "R115": "100R", "R116": "49.9R", "R117": "100R"}
DMIN, DMAX = 3, 6

class S:  # a strip
    n = 0
    def __init__(self, netname): S.n += 1; self.id = S.n; self.net = netname

def occ(strips, netname): return [i for i, s in enumerate(strips) if s.net == netname]
def ok_pair(strips, a, b):
    return any(DMIN <= abs(i - j) <= DMAX for i in occ(strips, a) for j in occ(strips, b))
def violations(strips): return sum(0 if ok_pair(strips, a, b) else 1 for _, a, b, _ in TWO)
def links(strips):
    nets = {}
    for s in strips: nets[s.net] = nets.get(s.net, 0) + 1
    return sum(v - 1 for v in nets.values())

def build(order, flips):
    strips, wins = [], {}
    for name, f in zip(order, flips):
        _, _, c, b, e = next(t for t in TRS if t[0] == name)
        tri = [e, b, c] if f else [c, b, e]
        if strips and strips[-1].net == tri[0]:
            ss = [strips[-1]] + [S(x) for x in tri[1:]]; strips += ss[1:]
        else:
            ss = [S(x) for x in tri]; strips += ss
        wins[name] = ss
    return strips, wins

def fix(strips):
    for _ in range(60):
        v0 = violations(strips)
        if v0 == 0: return True
        bad = [(r, a, b) for r, a, b, _ in TWO if not ok_pair(strips, a, b)]
        best = None
        for r, a, b in bad[:3]:
            for X, Y in ((a, b), (b, a)):
                for k in (occ(strips, Y) or [None]):
                    cands = ([k + d for d in range(DMIN, DMAX + 1)] + [k - d for d in range(DMIN, DMAX + 1)]) if k is not None else [len(strips)]
                    for p in cands:
                        if p < 0 or p > len(strips): continue
                        t = strips[:p] + [S(X)] + strips[p:]
                        sc = (violations(t), len(t) + 2 * links(t))
                        if best is None or sc < best[0]: best = (sc, t)
        if best is None: return False
        strips[:] = best[1]
    return violations(strips) == 0

def evaluate(order, flips):
    strips, wins = build(order, flips)
    if not fix(strips): return None
    return len(strips) + 3 * links(strips), strips, wins, order, flips

def search(seconds, seed):
    rnd = random.Random(seed); names = [t[0] for t in TRS]; best = None; t0 = time.time(); n = 0
    while time.time() - t0 < seconds * 0.3:
        order = names[:]; rnd.shuffle(order); flips = [rnd.random() < .5 for _ in order]
        r = evaluate(order, flips); n += 1
        if r and (best is None or r[0] < best[0]): best = r; print(f"  random {n}: rows {len(r[1])} links {links(r[1])} score {r[0]}", flush=True)
    cur = best
    while time.time() - t0 < seconds:       # local search: swap / move / flip, accept equal or better
        order, flips = cur[3][:], cur[4][:]
        m = rnd.random()
        i, j = rnd.randrange(len(order)), rnd.randrange(len(order))
        if m < .4: order[i], order[j] = order[j], order[i]; flips[i], flips[j] = flips[j], flips[i]
        elif m < .8: x = order.pop(i); f = flips.pop(i); order.insert(j, x); flips.insert(j, f)
        else: flips[i] = not flips[i]
        r = evaluate(order, flips)
        if r and r[0] <= cur[0]:
            if r[0] < cur[0]: print(f"  local: rows {len(r[1])} links {links(r[1])} score {r[0]}", flush=True)
            cur = r
            if r[0] < best[0]: best = r
    return best

def place(strips, wins, k=None):
    """columns for every component (first fit; row intervals must not overlap in a column), wires and pads. With k the design is folded into two regions
    side by side (rows < k on the left, rows >= k on the right, separated by a drilled column): the board needs max(k, N-k) strips instead of N."""
    N = len(strips); idx = {s_.id: i for i, s_ in enumerate(strips)}
    reg = (lambda r: 0 if (k is None or r < k) else 1)
    used = {}
    base = {0: 1, 1: None}
    out = {"tr": {}, "two": {}, "links": [], "pads": {}, "k": k, "N": N}
    def free(c, r0, r1): return all(r1 < a_ or r0 > b_ for a_, b_ in used.get(c, []))
    def take(r0, r1, lo):
        c = lo
        while not free(c, r0, r1): c += 1
        used.setdefault(c, []).append((r0, r1)); return c
    lo = {0: 2, 1: None}
    # region 0 first, to know its width
    comps = [("tr", n_, ss) for n_, ss in wins.items()]
    for n_, ss in wins.items():
        rows = [idx[x.id] for x in ss]
        if len({reg(r) for r in rows}) > 1: return None            # a transistor straddles the fold
    pick = {}
    for r_, a_, b_, v_ in TWO:
        best = None
        for i in occ(strips, a_):
            for j in occ(strips, b_):
                if DMIN <= abs(i - j) <= DMAX and reg(i) == reg(j) and (best is None or abs(i - j) < abs(best[0] - best[1])): best = (i, j)
        if best is None: return None
        pick[r_] = best
    width0 = 0
    for region in (0, 1) if k is not None else (0,):
        start = 2 if region == 0 else width0 + 3
        for n_, ss in wins.items():
            rows = [idx[x.id] for x in ss]
            if reg(rows[0]) == region: out["tr"][n_] = (take(min(rows), max(rows), start), rows)
        for r_, (i, j) in pick.items():
            if reg(i) == region: out["two"][r_] = (take(min(i, j), max(i, j), start), (i, j))
        bynet = {}
        for i, s_ in enumerate(strips):
            if reg(i) == region: bynet.setdefault(s_.net, []).append(i)
        for nm, rows in bynet.items():
            for r0, r1 in zip(rows, rows[1:]):
                c = start
                while not (free(c, r0, r0) and free(c, r1, r1)): c += 1
                used.setdefault(c, []).append((r0, r0)); used[c].append((r1, r1)); out["links"].append((nm, r0, r1, c, c))
        if region == 0 and k is not None: width0 = max(used) if used else 0
    # links between the regions (same net on both sides): one wire from a free hole of each region
    if k is not None:
        left = {}; right = {}
        for i, s_ in enumerate(strips): (left if reg(i) == 0 else right).setdefault(s_.net, []).append(i)
        for nm in set(left) & set(right):
            r0, r1 = left[nm][-1], right[nm][0]
            c0 = 2
            while not free(c0, r0, r0): c0 += 1
            c1 = width0 + 3
            while not free(c1, r1, r1): c1 += 1
            used.setdefault(c0, []).append((r0, r0)); used.setdefault(c1, []).append((r1, r1)); out["links"].append((nm, r0, r1, c0, c1))
    pads = (("+9V", "9V pad (plug 7)"), ("GND", "GND pad (plug 4)"), ("IN-", "IN- pad (plug 2)"), ("IN+", "IN+ pad (plug 3)"), ("OUT", "OUT pad (plug 6)"), ("ISET", "ISET pad (plug 8)"), ("NULL1", "NULL1 pad (plug 1)"), ("NULL5", "NULL5 pad (plug 5)"))
    for nm, lab in pads:
        r = occ(strips, nm)[0]; start = 2 if reg(r) == 0 else width0 + 3
        c = take(r, r, start); out["pads"][nm] = (c, r, lab)
    out["cols"] = max(used) + 1; out["width0"] = width0
    return out

def fold(strips, wins):
    """fold the design in two halves; a strip shared by two windows at the fold gets a copy (one more wire)"""
    best = None
    for p in range(len(strips) // 2 - 9, len(strips) // 2 + 10):
        s_ = strips[p]
        owners = [n for n, ss in wins.items() if any(x is s_ for x in ss)]
        cands = []
        if len(owners) == 2:
            B = [n for n in owners if wins[n][0] is s_]
            if B:
                new = S(s_.net); st2 = strips[:p + 1] + [new] + strips[p + 1:]
                w2 = {n: ([new] + ss[1:] if n == B[0] else ss) for n, ss in wins.items()}
                cands.append((st2, w2, p + 1))
        if not cands:
            cands.append((strips, wins, p + 1))
        for st2, w2, k in cands:
            pl = place(st2, w2, k)
            if pl is None: continue
            sc = max(k, len(st2) - k) + 0.5 * (len(st2) - len(strips))
            if best is None or sc < best[0]: best = (sc, k, pl, st2, w2)
    return best

def verify(strips, wins, pl):
    """connectivity of the placed layout (strips + wire links, components do not join strips) against the simulated netlist"""
    parent = {}
    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for nm, r0, r1, c0, c1 in pl["links"]: parent[find(("s", r0))] = find(("s", r1))
    row_net = {i: s.net for i, s in enumerate(strips)}
    comp = {}
    for i, s in enumerate(strips): comp.setdefault(find(("s", i)), set()).add(s.net)
    ok = True
    for k, v in comp.items():
        if len(v) > 1: print("SHORT: strips of different nets joined", v); ok = False
    for nm in set(row_net.values()):
        if len({find(("s", i)) for i, n in row_net.items() if n == nm}) != 1: print("NET NOT JOINED", nm); ok = False
    for name, (c, rows) in pl["tr"].items():
        _, _, tc, tb, te = next(t for t in TRS if t[0] == name)
        have = [row_net[r] for r in rows]
        if have not in ([tc, tb, te], [te, tb, tc]): print("TRANSISTOR", name, have); ok = False
    for r, a, b, v in TWO:
        i, j = pl["two"][r][1]
        if {row_net[i], row_net[j]} != {a, b}: print("RESISTOR", r); ok = False
    occupied = {}
    for name, (c, rows) in pl["tr"].items():
        for r in rows:
            if (r, c) in occupied: print("HOLE TWICE", (r, c), name, occupied[(r, c)]); ok = False
            occupied[(r, c)] = name
    for r, (c, (i, j)) in pl["two"].items():
        for rr in (i, j):
            if (rr, c) in occupied: print("HOLE TWICE", (rr, c), r, occupied[(rr, c)]); ok = False
            occupied[(rr, c)] = r
    print("layout verified against the netlist" if ok else "LAYOUT ERRORS")
    return ok

def draw(strips, pl, path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle
    N, k, C = pl["N"], pl["k"], pl["cols"]
    S = max(k, N - k) if k else N
    start = lambda r: 0 if (k is None or r < k) else k
    fig, ax = plt.subplots(figsize=(max(11, C * 0.55 + 6), S * 0.42 + 1.8))
    y = lambda r: S - (r - start(r))
    for r, s_ in enumerate(strips):
        x0 = 0.5 if (k is None or r < k) else pl["width0"] + 2.5
        x1 = (pl["width0"] + 0.5 if k else C + 0.7) if (k is None or r < k) else C + 0.7
        ax.add_patch(Rectangle((x0, y(r) - 0.34), x1 - x0, 0.68, color="#d9a76b", alpha=.5, lw=0))
        lx = x0 - 0.2 if (k is None or r < k) else x0 - 0.2
        ax.text(lx, y(r), s_.net, ha="right", va="center", fontsize=7.5, weight="bold", zorder=9, bbox=dict(fc="white", ec="none", alpha=.7, pad=.3))
    for c in range(1, C + 1):
        for r in range(N):
            if k and c == pl["width0"] + 1: continue
            if k is not None and r >= k and c <= pl["width0"] + 2: continue
            if k is not None and r < k and c > pl["width0"]: continue
            ax.add_patch(Circle((c, y(r)), 0.11, color="white", ec="#666", lw=.5, zorder=3))
    if k:
        for sidx in range(S): ax.plot(pl["width0"] + 1, S - sidx, "rx", ms=8, mew=2, zorder=8)
    for name, (c, rows) in pl["tr"].items():
        tt = next(t for t in TRS if t[0] == name); typ = tt[1]
        nets = [strips[r].net for r in rows]
        pin = ["C" if n_ == tt[2] else "E" if n_ == tt[4] else "B" for n_ in nets]
        if tt[2] == tt[3]: pin = ["C", "B", "E"] if nets[2] == tt[4] else ["E", "B", "C"]
        for r, p in zip(rows, pin): ax.add_patch(Circle((c, y(r)), 0.27, color="#2b2b2b" if typ == "NPN" else "#7a3b8f", zorder=5)); ax.text(c, y(r), p, color="white", ha="center", va="center", fontsize=6, zorder=6, weight="bold")
        ax.text(c + 0.45, y(rows[1]), f"{name} {typ}", fontsize=6.3, va="center", zorder=7, bbox=dict(fc="white", ec="none", alpha=.8, pad=.4))
    for r, (c, (i, j)) in pl["two"].items():
        ax.plot([c, c], [y(i), y(j)], "-", color="#b5651d" if r[0] == "R" else "#1f77b4", lw=6, solid_capstyle="round", zorder=4, alpha=.9)
        ax.text(c + 0.4, (y(i) + y(j)) / 2, f"{r} {VALUE.get(r, '39p')}", fontsize=6.3, va="center", zorder=7, bbox=dict(fc="white", ec="none", alpha=.85, pad=.4))
    for nm, r0, r1, c0, c1 in pl["links"]:
        ax.plot([c0, c1], [y(r0), y(r1)], "-", color="#2ca02c", lw=2.2, zorder=6); ax.plot([c0, c1], [y(r0), y(r1)], "o", color="#2ca02c", ms=4.5, zorder=6)
    for nm, (c, r, lab) in pl["pads"].items():
        ax.add_patch(Circle((c, y(r)), 0.3, fc="none", ec="k", lw=2, zorder=7)); ax.text(c + 0.4, y(r) + 0.33, lab, fontsize=6.3, zorder=8, bbox=dict(fc="white", ec="none", alpha=.85, pad=.3))
    ax.set_xlim(-7, C + 2.2); ax.set_ylim(0.2, S + 0.9); ax.axis("off")
    ax.set_title(f"LM4250 clone on stripboard — {S} strips x {C} holes, component side. Strips are labelled with their net.\nBrown = resistor, blue = Cc, green = wire links (also between the two halves), circles = flying-lead pads, red X = drill the strip in that column (separates the two halves).\nOrient each TO-92 so that C/B/E fall on the rows marked C/B/E (rotate it 180 degrees if your pinout is the other way: check the datasheet).", fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1; secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60
    best = search(secs, seed)
    sc, strips, wins, order, flips = best
    f = fold(strips, wins)
    if f: strips, wins, pl = f[3], f[4], f[2]
    else: pl = place(strips, wins)
    print("folded at row", pl["k"], "->", max(pl["k"], len(strips) - pl["k"]) if pl["k"] else len(strips), "strips")
    if verify(strips, wins, pl):
        draw(strips, pl, "../docs/VEROBOARD-CLONE.png")
        import json
        json.dump(dict(rows=[s.net for s in strips], cols=pl["cols"], transistors={k: [v[0], v[1]] for k, v in pl["tr"].items()}, two={k: [v[0], v[1]] for k, v in pl["two"].items()}, links=[list(l) for l in pl["links"]], k=pl["k"], pads={k: list(v) for k, v in pl["pads"].items()}), open("veroboard_clone.json", "w"), indent=1)
        print(f"rows {len(strips)}  cols {pl['cols']}  links {len(pl['links'])}  score {sc}")

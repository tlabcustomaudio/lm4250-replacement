"""Stripboard layout of the OPA333 module (78L05 floating-window version) + automatic check against the schematic's nets.
Strips run along the rows (A..I = 9 strips), 20 holes per strip, component-side view.   uv run --with matplotlib python veroboard.py"""
import itertools
ROWS = "ABCDEFGHI"; COLS = 20
CUTS = {("C", 8), ("D", 8)}                       # holes drilled through (the strip is interrupted there)
# component pins: name -> (row, col)
PINS = {
 "U2.1": ("B", 7), "U2.2": ("C", 7), "U2.3": ("D", 7), "U2.4": ("E", 7), "U2.5": ("E", 10), "U2.6": ("D", 10), "U2.7": ("C", 10), "U2.8": ("B", 10),   # DIP-8 socket
 "R1.a": ("E", 3), "R1.b": ("I", 3),            # 1k3  : VM - 9V
 "R2.a": ("A", 5), "R2.b": ("E", 5),            # 220R : GND - VM
 "C1.-": ("A", 2), "C1.+": ("E", 2),            # 47u  : GND - VM
 "C4.a": ("I", 9), "C4.b": ("E", 9),            # 330n : 9V - VM
 "C2.a": ("C", 13), "C2.b": ("E", 13),          # 1u   : VREG - VM
 "C3.a": ("C", 12), "C3.b": ("E", 12),          # 100n : VREG - VM
 "U1.1": ("F", 16), "U1.2": ("G", 16), "U1.3": ("H", 16),   # 78L05 TO-92: 1 OUT, 2 GND, 3 IN (HT7550: see notes)
 "J9V": ("I", 1), "JGND": ("A", 1), "JIN-": ("C", 1), "JIN+": ("D", 1), "JOUT": ("D", 18),   # solder pads for the flying leads
}
LINKS = [(("F", 19), ("C", 19)), (("G", 19), ("E", 19)), (("H", 19), ("I", 19))]            # jumper wires over the board
EXPECT = {  # net -> pins that must be on it
 "9V":   ["J9V", "R1.b", "C4.a", "U1.3"], "GND": ["JGND", "R2.a", "C1.-"],
 "VM":   ["U2.4", "U2.5", "R1.a", "R2.b", "C1.+", "C4.b", "C2.b", "C3.b", "U1.2"],
 "VREG": ["U2.7", "C2.a", "C3.a", "U1.1"], "IN-": ["JIN-", "U2.2"], "IN+": ["JIN+", "U2.3"], "OUT": ["JOUT", "U2.6"], "NC": ["U2.1", "U2.8"],
}

def nets():
    parent = {}
    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    for r in ROWS:                                  # strips
        for c in range(1, COLS):
            if (r, c) in CUTS or (r, c + 1) in CUTS: continue
            union((r, c), (r, c + 1))
    for a, b in LINKS: union(a, b)
    return find

def check():
    find = nets()
    where = {n: [find(PINS[p]) for p in ps] for n, ps in EXPECT.items()}
    ok = True
    for n, ids in where.items():
        if len(set(ids)) != 1: print("NOT CONNECTED:", n, [(p, PINS[p]) for p in EXPECT[n]]); ok = False
    for (a, ia), (b, ib) in itertools.combinations(where.items(), 2):
        if ia[0] == ib[0]: print("SHORT between", a, "and", b); ok = False
    occupied = {}
    for p, pos in PINS.items():
        if pos in occupied: print("HOLE USED TWICE", pos, p, occupied[pos]); ok = False
        occupied[pos] = p
    print("layout matches the schematic nets" if ok else "LAYOUT ERRORS")
    return ok

def draw(path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle
    fig, ax = plt.subplots(figsize=(15, 7.6))
    y = {r: len(ROWS) - i for i, r in enumerate(ROWS)}
    for r in ROWS:
        ax.add_patch(Rectangle((0.5, y[r] - 0.32), COLS, 0.64, color="#d9a76b", alpha=.55, lw=0))
        ax.text(0.1, y[r], r, ha="center", va="center", fontsize=10, weight="bold")
        for c in range(1, COLS + 1):
            ax.add_patch(Circle((c, y[r]), 0.16, color="white", ec="#555", lw=.6, zorder=3))
    for c in range(1, COLS + 1): ax.text(c, len(ROWS) + 0.85, str(c), ha="center", fontsize=8)
    for r, c in CUTS: ax.plot(c, y[r], "rx", ms=13, mew=3, zorder=8); ax.add_patch(Circle((c, y[r]), 0.2, fc="none", ec="red", lw=2, zorder=8))
    # socket
    ax.add_patch(Rectangle((6.6, y["E"] - 0.45), 3.8, 4 * 1.0 - 0.1, fc="#2b2b2b", alpha=.55, zorder=4)); ax.text(8.5, y["A"] - 0.62 + 0.0, "DIP-8 socket (adapter + OPA333) - pin 1 up, left column", ha="center", color="k", fontsize=8, zorder=7)
    for p in ("U2.1", "U2.2", "U2.3", "U2.4", "U2.5", "U2.6", "U2.7", "U2.8"):
        r, c = PINS[p]; ax.text(c, y[r], p[-1], ha="center", va="center", color="yellow", fontsize=8, zorder=8, weight="bold")
    def two(a, b, label, color):
        (r1, c1), (r2, c2) = PINS[a], PINS[b]
        ax.plot([c1, c2], [y[r1], y[r2]], "-", color=color, lw=9, solid_capstyle="round", zorder=5, alpha=.9)
        ax.text((c1 + c2) / 2 + .45, (y[r1] + y[r2]) / 2 + (0.0), label, fontsize=9, zorder=9, weight="bold", bbox=dict(fc="white", ec="none", alpha=.85, pad=1.2))
    two("R1.a", "R1.b", "R1 1k3", "#b5651d"); two("R2.a", "R2.b", "R2 220R", "#b5651d")
    two("C1.-", "C1.+", "C1 47µ\n(+ on E)", "#1f77b4"); two("C4.a", "C4.b", "C4 330n", "#7fb3d5"); two("C2.a", "C2.b", "C2 1µ", "#7fb3d5"); two("C3.a", "C3.b", "C3 100n", "#7fb3d5")
    for p, lab in (("U1.1", "1 OUT"), ("U1.2", "2 GND"), ("U1.3", "3 IN")):
        r, c = PINS[p]; ax.add_patch(Circle((c, y[r]), 0.3, color="#444", zorder=5)); ax.text(c + .5, y[r], lab, fontsize=8, va="center", zorder=9)
    ax.text(16, y["F"] + 0.7, "78L05 (TO-92, flat side per datasheet)", ha="center", fontsize=8)
    for a, b in LINKS:
        ax.plot([a[1], b[1]], [y[a[0]], y[b[0]]], "-", color="#2ca02c", lw=3, zorder=6)
    for p, lab in (("J9V", "+9V lead (plug 7)"), ("JGND", "GND lead (plug 4)"), ("JIN-", "IN− lead (plug 2)"), ("JIN+", "IN+ lead (plug 3)"), ("JOUT", "OUT lead (plug 6)")):
        r, c = PINS[p]; ax.add_patch(Circle((c, y[r]), 0.28, fc="none", ec="k", lw=2, zorder=7)); ax.text(c + (0.45 if p != "JOUT" else -0.45), y[r] + 0.42, lab, fontsize=8, va="center", ha="left" if p != "JOUT" else "right", zorder=9, bbox=dict(fc="white", ec="none", alpha=.9, pad=1))
    ax.set_xlim(-0.3, COLS + 1); ax.set_ylim(0.2, len(ROWS) + 1.4); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("OPA333 module on stripboard — component side, strips run along the rows A–I (20 holes). Red X = drill/cut the strip at that hole. Green = wire jumpers over the board.", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)

if __name__ == "__main__":
    import sys
    if check() and "draw" in sys.argv: draw("../../docs/VEROBOARD-OPA333-MODULE.png"); print("figure saved")

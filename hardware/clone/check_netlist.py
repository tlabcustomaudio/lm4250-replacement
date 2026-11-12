"""KiCad schematic netlist == the SPICE netlist simulated in sim/clone.py ? (connectivity only, node names ignored)"""
import re, sys, xml.etree.ElementTree as ET
sys.path.insert(0, "../sim")  # run from hardware/ after exporting the netlist: kicad-cli sch export netlist --format kicadxml -o out/n.xml LM4250_CLONE.kicad_sch
import clone
spice = {}
for ln in clone.SUB.splitlines():
    t = ln.split()
    if not t or t[0].startswith((".", "*")) or t[0] == "Cc":
        continue
    ref = t[0] if t[0][0] != "Q" else t[0]
    if ref[0] == "Q":
        pins = dict(zip("CBE", t[1:4]))
    elif ref[0] == "R":
        pins = {"1": t[1], "2": t[2]}
    for p, n in pins.items():
        spice.setdefault(n, set()).add((ref, p))
cc = [l.split() for l in clone.SUB.splitlines() if l.startswith("Cc")][0]
spice.setdefault(cc[1], set()).add(("C1", "1")); spice.setdefault(cc[2], set()).add(("C1", "2"))
ports = {"in_n": ("J1", "2"), "in_p": ("J1", "3"), "vp": ("J1", "7"), "vn": ("J1", "4"), "out": ("J1", "6"), "iset": ("J1", "8"), "n1": ("J1", "1"), "n5": ("J1", "5")}
for n, pin in ports.items():
    spice.setdefault(n, set()).add(pin)
ren = lambda r: r[0] + str(int(r[1:]) + 100) if r[0] in "QRC" and r[1:].isdigit() else r
spice = {n: {(ren(r), p) for r, p in v} for n, v in spice.items()}   # the clone parts are numbered +100 in the schematic
kic = {}
for net in ET.parse("out/n.xml").getroot().iter("net"):
    pins = {(nd.get("ref"), {"B": "B", "C": "C", "E": "E"}.get(nd.get("pin"), nd.get("pin"))) for nd in net.iter("node") if not nd.get("ref").startswith("#")}
    if pins:
        kic[net.get("name")] = pins
# SPICE: Q pins are C,B,E letters; R pins 1,2;  KiCad: Q pins B/C/E letters, R 1/2  -> same
norm = lambda v: frozenset((r, 'x' if r[0] in 'RC' else p) for r, p in v)   # two-terminal parts: pin order is irrelevant
A = {norm(v) for v in spice.values() if len(v) > 1}
B = {norm(v) for v in kic.values() if len(v) > 1}
print("nets spice", len(A), "kicad", len(B))
print("only in spice:", [sorted(x) for x in A - B])
print("only in kicad:", [sorted(x) for x in B - A])

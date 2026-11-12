"""Circuit simulation for R&D: a KiCad XML netlist (kicad-cli sch export netlist --format kicadxml) -> ngspice.
parse(xml) reads the parts and guesses input/output/supplies; ac() = frequency response IN -> OUT at given knob/switch
settings; tran() = audio samples through the circuit. Parts with no model are listed in parse()['missing'] and must be
skipped or overridden ({ref: "skip"} / {ref: "<value or model>"} / {ref: "<raw spice line with {n1} {n2}...>"}).
Check: test_spice.py (micromamba run -n spice python test_spice.py, or in the container)."""
import math
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET


class SimError(Exception):
    pass


MODELS = """
.model 1N4148 D(IS=2.52n RS=0.568 N=1.752 CJO=4p TT=20n BV=100)
.model 1N914 D(IS=2.52n RS=0.568 N=1.752 CJO=4p TT=20n BV=100)
.model 1N34A D(IS=2.6u RS=4 N=1.6 CJO=1p BV=60)
.model 1N5817 D(IS=31.7u RS=0.051 N=1.373 CJO=190p BV=20)
.model BAT41 D(IS=4n RS=7 N=1.03 CJO=2p BV=100)
.model BAT46 D(IS=1.2n RS=5 N=1.0 CJO=10p BV=100)
.model 1N4001 D(IS=14n RS=0.034 N=1.98 CJO=26p BV=75)
.model LED D(IS=1e-20 RS=3 N=1.8 CJO=40p BV=5)
.model GEND D(IS=2.6u RS=4 N=1.6)
.model 2N3904 NPN(IS=6.7f BF=416 VAF=74 IKF=66m RB=10 RC=1 CJE=4.5p CJC=3.6p TF=301p)
.model 2N2222 NPN(IS=14f BF=256 VAF=74 IKF=0.28 RB=10 RC=1 CJE=22p CJC=7.3p TF=411p)
.model 2N5088 NPN(IS=5.9f BF=1122 VAF=63 IKF=14m RB=10 RC=1.6 CJE=4.5p CJC=4p TF=820p)
.model 2N5089 NPN(IS=5.9f BF=1434 VAF=63 IKF=14m RB=10 RC=1.6 CJE=4.5p CJC=4p TF=820p)
.model BC549 NPN(IS=7f BF=490 VAF=30 IKF=0.1 RB=10 RC=1 CJE=12p CJC=4p TF=500p)
.model BC109 NPN(IS=7f BF=400 VAF=50 RB=10 RC=1 CJE=12p CJC=4p)
.model MPSA18 NPN(IS=5f BF=1200 VAF=80 RB=10 RC=1 CJE=5p CJC=4p)
.model 2SC1815 NPN(IS=2f BF=300 VAF=100 RB=10 RC=1 CJE=8p CJC=3p)
.model 2SC828 NPN(IS=5f BF=250 VAF=100 RB=10 RC=1 CJE=8p CJC=3p)
.model 2SC900 NPN(IS=5f BF=600 VAF=100 RB=10 RC=1 CJE=8p CJC=3p)
.model 2SC2240 NPN(IS=3f BF=400 VAF=100 RB=10 RC=1 CJE=8p CJC=3p)
.model 2SC732 NPN(IS=5f BF=400 VAF=100 RB=10 RC=1 CJE=8p CJC=3p)
.model GNPN NPN(IS=10f BF=300 VAF=100 RB=10 RC=1 CJE=8p CJC=4p)
.model 2N3906 PNP(IS=1.4f BF=180 VAF=18.7 RB=10 RC=2.5 CJE=4.5p CJC=4.5p)
.model BC559 PNP(IS=10f BF=400 VAF=30 RB=10 RC=1 CJE=12p CJC=6p)
.model AC128 PNP(IS=20u BF=90 VAF=30 RB=50 RC=2 CJE=50p CJC=30p)
.model GPNP PNP(IS=10f BF=250 VAF=60 RB=10 RC=1 CJE=8p CJC=4p)
.model J201 NJF(VTO=-0.8 BETA=1.3m LAMBDA=4m IS=1e-14 CGS=4p CGD=1.6p)
.model 2N5457 NJF(VTO=-1.37 BETA=1.13m LAMBDA=2.3m IS=1e-14 CGS=4p CGD=4p)
.model 2N5952 NJF(VTO=-2.5 BETA=1.6m LAMBDA=4m IS=1e-14 CGS=4p CGD=4p)
.model MPF102 NJF(VTO=-3 BETA=0.8m LAMBDA=3m IS=1e-14 CGS=4p CGD=4p)
.model 2SK30 NJF(VTO=-1.5 BETA=1.8m LAMBDA=3m IS=1e-14 CGS=4p CGD=4p)
.model 2SK117 NJF(VTO=-0.9 BETA=5.5m LAMBDA=5m IS=1e-14 CGS=8p CGD=3p)
.model GNJF NJF(VTO=-2 BETA=1m LAMBDA=3m IS=1e-14 CGS=4p CGD=2p)
.model DCLAMP D(IS=1e-15 N=0.1)
.subckt OPAMP inp inn vp vn out params: gbw=1Meg
* 100 dB open loop, one pole at gbw/1e5, output clamped 1.5 V inside the rails
Rin inp inn 10Meg
G1 0 n1 inp inn 1e-3
R1 n1 0 1e8
C1 n1 0 {1e-3/(6.2832*gbw)}
Bo n2 0 V = max(min(v(n1), v(vp)-1.5), v(vn)+1.5)
Ro n2 out 50
Rq vp vn 5k
.ends
"""
DIODES = ["1N4148", "1N914", "1N34A", "1N5817", "BAT41", "BAT46", "1N4001", "1N400"]
NPNS = ["2SC2240", "2N3904", "2N2222", "2N5088", "2N5089", "BC549", "BC550", "BC109", "MPSA18", "2SC1815", "2SC828", "2SC900", "2SC732"]
PNPS = ["2N3906", "BC559", "AC128"]
JFETS = ["2SK117", "2SK30", "J201", "2N5457", "2N5952", "MPF102"]
OPAMPS = [("TL07", "3Meg"), ("TL06", "1Meg"), ("4558", "3Meg"), ("741", "1Meg"), ("LM471", "1Meg"), ("TA7136", "1Meg"), ("NE5532", "10Meg"), ("5532", "10Meg"),
          ("LM358", "1Meg"), ("OPA2134", "8Meg"), ("OPA134", "8Meg"), ("LF35", "4Meg"), ("CA3130", "15Meg"), ("LM308", "1Meg"),
          ("TLC227", "2Meg"), ("TL08", "3Meg"), ("LM324", "1Meg"), ("OPA4134", "8Meg")]
QUAD = r"TL0[678]4|TLC2274|TLC2254|LM324|LM348|MC3403|OPA4|4136"  # DIP-14: 3+ 2- 1 / 5+ 6- 7 / 10+ 9- 8 / 12+ 13- 14, V+ 4, V- 11
ALIAS = {"BC550": "BC549", "1N400": "1N4001"}


def value(s):
    """KiCad value -> SPICE: '4k7 (note)' -> '4.7k', '2M2' -> '2.2Meg', '680R' -> '680', '10uF' -> '10u'."""
    s = re.split(r"[\s(]", (s or "").strip(), 1)[0]
    s = re.sub(r"(?i)(?<=[0-9pnumkKM])F$", "", s).replace("µ", "u")
    m = re.fullmatch(r"(\d+)([pnumkKMR])(\d+)", s)
    if m:
        s = f"{m[1]}.{m[3]}{m[2]}"
    s = re.sub(r"R$", "", s)
    return re.sub(r"M$", "Meg", s)


def num(s):
    m = re.fullmatch(r"([\d.]+)(Meg|[pnumkK])?", value(s))
    if not m:
        raise ValueError(s)
    return float(m[1]) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "Meg": 1e6, None: 1}[m[2]]


def pot(s):
    """'100kA' / 'A100k' / 'B50k' / '5kA O JUMPER' -> (ohms, taper)."""
    tok = (s or "").split()[0] if (s or "").split() else ""
    m = re.fullmatch(r"([ABC])?([\d.]+[kKM]?\d*)([ABC])?", tok)
    if not m:
        raise ValueError(s)
    return num(m[2]), (m[1] or m[3] or "B")


def taper(t, pos):
    pos = min(max(float(pos), 0.0), 1.0)
    a = lambda p: (10 ** (2 * p) - 1) / 99
    return {"A": a(pos), "C": 1 - a(1 - pos)}.get(t, pos)


def known(text, names):
    t = (text or "").upper()
    hits = [(t.find(n.upper()), n) for n in names if n.upper() in t]
    return ALIAS.get(min(hits)[1], min(hits)[1]) if hits else None


def kind_of(ref, val, part):
    r, p, v = re.match(r"[A-Za-z]*", ref)[0].upper(), (part or "").upper(), (val or "").upper()
    if r in ("RV", "VR") or "POT" in p:
        return "pot"
    if r == "R":
        return "resistor"
    if r == "C":
        return "capacitor"
    if r == "L":
        return "inductor"
    if r == "SW" or p.startswith("SW_"):
        return "switch"
    if r == "JP":
        return "jumper"
    if r == "D" or "LED" in p:
        return "diode"
    if r == "Q":
        if "JFET" in p or "NJF" in p or "PJF" in p or known(v, JFETS):
            return "jfet"
        return "bjt"
    if r == "J":
        return "connector"
    if r in ("U", "IC") and known(v + " " + p, [n for n, _ in OPAMPS]):
        return "opamp"
    return "other"


def node(net):
    if re.match(r"(?i)^(gnd|0$|vss$)", net):
        return "0"
    return re.sub(r"\W", "_", net.replace("+", "_p").replace("-", "_m")).strip("_") or "n"  # V+ / V- / V stay distinct


def parse(xml_text):
    root = ET.fromstring(xml_text)
    parts = {}
    for c in root.iter("comp"):
        ls = c.find("libsource")
        ref, val = c.get("ref"), (c.findtext("value") or "")
        part = ls.get("part") if ls is not None else ""
        parts[ref] = {"ref": ref, "value": val, "lib": ls.get("lib") if ls is not None else "", "part": part,
                      "kind": kind_of(ref, val, part), "pins": {}, "model": None}
    nets = []
    for n in root.iter("net"):
        nets.append(n.get("name"))
        for nd in n.iter("node"):
            if nd.get("ref") in parts:
                parts[nd.get("ref")]["pins"][nd.get("pin")] = {"net": n.get("name"), "name": nd.get("pinfunction") or ""}
    pick = lambda pat: next((n for n in nets if re.fullmatch(pat, n, re.I)), None)
    supplies = {}
    for n in nets:
        if re.match(r"(?i)^(gnd|0$|vss$)", n):
            continue
        m = re.fullmatch(r"(?i)([+-]?)(\d+(?:[.,]\d+)?)V\d*", n)
        if m:
            supplies[n] = (-1 if m[1] == "-" else 1) * float(m[2].replace(",", "."))
        elif re.fullmatch(r"(?i)V\+|VCC|VBAT|VDD|V|VIN|DC", n):
            supplies[n] = 9.0
        elif re.fullmatch(r"(?i)V-|VEE", n):
            supplies[n] = -9.0
    missing = []
    for p in parts.values():
        k, v = p["kind"], p["value"]
        if k == "diode":
            p["model"] = "LED" if "LED" in (p["part"] + v).upper() else known(v, DIODES) or ("GEND" if "GE" in v.upper() else "1N4148")
        elif k == "bjt":
            pnp = "PNP" in p["part"].upper() or known(v, PNPS)
            p["model"] = known(v, PNPS if pnp else NPNS) or ("GPNP" if pnp else "GNPN")
        elif k == "jfet":
            p["model"] = known(v, JFETS) or "GNJF"
        elif k == "opamp":
            name = known(v + " " + p["part"], [n for n, _ in OPAMPS])
            p["model"] = dict(OPAMPS)[name]
        elif k == "other" and p["pins"]:
            missing.append({"ref": p["ref"], "value": v, "part": p["part"], "reason": "nessun modello SPICE"})
    order = lambda r: (re.match(r"\D*", r)[0], int(re.search(r"\d+", r)[0]) if re.search(r"\d+", r) else 0)
    missing.sort(key=lambda m: order(m["ref"]))
    return {"parts": sorted(parts.values(), key=lambda p: order(p["ref"])), "nets": nets, "missing": missing,
            "in": pick(r"IN|INPUT|IN\+"), "out": pick(r"OUT|OUTPUT|OUT\+"), "supplies": supplies}


def pin_by(p, *names):
    for n in names:
        for num_, pi in p["pins"].items():
            if re.sub(r"_\d+$", "", pi["name"]).upper() == n:
                return node(pi["net"])
    return None


def lines(parsed, settings, overrides):
    out, settings, overrides = [], settings or {}, overrides or {}
    todo = [m["ref"] for m in parsed["missing"] if m["ref"] not in overrides]
    if todo:
        raise SimError("parti senza modello: " + ", ".join(todo) + " (salta o scrivi un modello)")
    for p in parsed["parts"]:
        ref, k, ov = p["ref"], p["kind"], overrides.get(p["ref"])
        if ov == "skip" or k == "connector" or not p["pins"]:
            continue
        nums = sorted(p["pins"], key=lambda s: int(s) if s.isdigit() else 0)
        n = [node(p["pins"][x]["net"]) for x in nums]
        try:
            if k == "other":
                out.append(re.sub(r"\{n(\d+)\}", lambda m: n[int(m[1]) - 1], ov))
            elif k in ("resistor", "capacitor", "inductor"):
                out.append(f"{ref} {n[0]} {n[1]} {value(ov or p['value'])}")
            elif k == "pot":
                ohms, t = pot(ov or p["value"])
                f = taper(t, settings.get(ref, 0.5))
                pin = {x: node(p["pins"][x]["net"]) for x in nums}
                out.append(f"{ref}a {pin.get('1', n[0])} {pin.get('2', n[1])} {max(ohms * f, 1):g}")
                out.append(f"{ref}b {pin.get('2', n[1])} {pin.get('3', n[-1])} {max(ohms * (1 - f), 1):g}")
            elif k in ("switch", "jumper"):
                on = int(settings.get(ref, 0))
                named = {re.sub(r"_\d+$", "", p["pins"][x]["name"]).upper() for x in nums}
                if {"A", "B", "C"} <= named:
                    for i in range(0, len(nums) - len(nums) % 3, 3):
                        tri = {re.sub(r"_\d+$", "", p["pins"][x]["name"]).upper(): node(p["pins"][x]["net"]) for x in nums[i:i + 3]}
                        out.append(f"R{ref}_{i // 3} {tri['B']} {tri['C' if on else 'A']} 0.01")
                elif len(n) >= 2 and on:
                    out.append(f"R{ref} {n[0]} {n[1]} 0.01")
            elif k == "diode":
                a, c = pin_by(p, "A") or n[-1], pin_by(p, "K") or n[0]
                out.append(f"D{ref} {a} {c} {ov or p['model']}")
            elif k == "bjt":
                c, b, e = pin_by(p, "C"), pin_by(p, "B"), pin_by(p, "E")
                out.append(f"Q{ref} {c or n[0]} {b or n[1]} {e or n[2]} {ov or p['model']}")
            elif k == "jfet":
                d, g, s = pin_by(p, "D"), pin_by(p, "G"), pin_by(p, "S")
                out.append(f"J{ref} {d or n[0]} {g or n[1]} {s or n[2]} {ov or p['model']}")
            elif k == "opamp":  # DIP-8: single 3+ 2- 6out, dual 3+ 2- 1out / 5+ 6- 7out, 7 or 8 = V+, 4 = V-; quad: QUAD
                pin = {x: node(p["pins"][x]["net"]) for x in nums}
                t = (p["value"] + " " + p["part"]).upper()
                quad = re.search(QUAD, t) is not None
                dual = not quad and re.search(r"72|4558|5532|358|2134|353|62|1458|082", t) is not None
                vp = pin_by(p, "V+") or pin.get("4" if quad else "8" if dual else "7")
                vn = pin_by(p, "V-") or pin.get("11" if quad else "4")
                units = ([("3", "2", "1"), ("5", "6", "7"), ("10", "9", "8"), ("12", "13", "14")] if quad else
                         [("3", "2", "1"), ("5", "6", "7")] if dual else [("3", "2", "6")])
                if "TA7136" in t:
                    units = [("2", "3", "6")]  # SIP-7: + on 2, - on 3
                for i, u in enumerate(units):
                    if all(x in pin for x in u):
                        out.append(f"X{ref}_{i} {pin[u[0]]} {pin[u[1]]} {vp} {vn} {pin[u[2]]} OPAMP params: gbw={ov or p['model']}")
        except (ValueError, KeyError, IndexError) as e:
            raise SimError(f"{ref} ({p['value']}): non capisco il valore o i pin ({e})")
    return out


def deck(parsed, settings, overrides, supplies, src, analysis):
    if not parsed["in"] or not parsed["out"]:
        raise SimError("non trovo le reti IN e OUT: chiamale così nello schema")
    body = lines(parsed, settings, overrides)
    sup = parsed["supplies"] if supplies is None else supplies
    body += [f"VS{i} {node(n)} 0 DC {v}" for i, (n, v) in enumerate(sup.items()) if node(n) != "0"]
    nodes = sorted({t for l in body for t in l.split()[1:3] if t != "0" and not t.startswith("{")} | {node(n) for n in parsed["nets"]} - {"0"})
    body += [f"RL_{x} {x} 0 1G" for x in nodes]
    i, o = node(parsed["in"]), node(parsed["out"])
    return "\n".join(["* stompdex", MODELS, f"VIN {i} 0 {src}", f"RLOAD {o} 0 1Meg", *body,
                      ".options method=gear reltol=1e-3 abstol=1e-10 vntol=1e-5 noacct", ".control", analysis, ".endc", ".end", ""]), o


def run(text, outfile):
    with tempfile.TemporaryDirectory() as d:
        cir = os.path.join(d, "c.cir")
        open(cir, "w").write(text.replace("@OUT@", os.path.join(d, outfile)))
        r = subprocess.run(["ngspice", "-b", cir], capture_output=True, text=True, timeout=600)
        path = os.path.join(d, outfile)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            err = [l for l in (r.stdout + r.stderr).splitlines() if re.search(r"(?i)error|fatal|singular|unknown|not found", l)]
            raise SimError("ngspice: " + ("; ".join(err[:6]) or "nessun risultato"))
        return [[float(x) for x in l.split()] for l in open(path) if l.strip() and not l.lstrip()[0].isalpha()]


def ac(parsed, settings=None, overrides=None, supplies=None, f0=20, f1=20000, points=60):
    text, o = deck(parsed, settings, overrides, supplies, "DC 0 AC 1", "")
    text = text.replace(".control\n\n", f".control\nac dec {points} {f0} {f1}\nwrdata @OUT@ db(mag(v({o}))+1e-12)\n")
    return [(r[0], r[1]) for r in run(text, "ac.txt")]


def tran(parsed, samples, sr, settings=None, overrides=None, supplies=None, rs=None):  # rs: source resistance in series with the file source (the engine drives IN through its own Rs, 10k by default)
    n, dt = len(samples), 1.0 / sr
    with tempfile.TemporaryDirectory() as d:
        pwl = os.path.join(d, "in.pwl")
        with open(pwl, "w") as f:
            f.writelines(f"{k * dt:.9g} {s:.6g}\n" for k, s in enumerate(samples))
        text, o = deck(parsed, settings, overrides, supplies, "DC 0", "")
        i = node(parsed["in"])  # XSPICE file source drives IN (VIN is rewritten into it)
        text = re.sub(rf"(?m)^VIN {i} 0 DC 0$", (f"RSRC SRC_IN {i} {rs}\n" if rs else "") + f"aVIN %vd([{'SRC_IN' if rs else i} 0]) filesrc\n.model filesrc filesource (file=\"{pwl}\" amploffset=[0] amplscale=[1] "
                      "timeoffset=0 timescale=1 timerelative=false amplstep=false)", text)
        text = text.replace(".control\n\n", f".control\ntran {dt:.9g} {n * dt:.9g} 0 {dt:.9g}\nlinearize v({o})\nwrdata @OUT@ v({o})\n")
        rows = run(text, "tr.txt")
    t = [r[0] for r in rows]
    v = [r[1] for r in rows]
    y, j = [], 0
    for k in range(n):  # resample at the input sample times
        tk = k * dt
        while j + 1 < len(t) - 1 and t[j + 1] < tk:
            j += 1
        if j + 1 < len(t) and t[j + 1] != t[j]:
            a = (tk - t[j]) / (t[j + 1] - t[j])
            y.append(v[j] + (v[j + 1] - v[j]) * min(max(a, 0), 1))
        else:
            y.append(v[min(j, len(v) - 1)])
    m = sum(y) / len(y)
    return [s - m for s in y]

# Simulation scripts

| File | What it does |
|---|---|
| `spice.py` | KiCad netlist (XML) → ngspice deck helper (resistors, capacitors, pots, op-amps, BJTs, JFETs) |
| `mm_v3.xml` | netlist of the Stingray-style preamp pedal (V3): U1 is the op-amp under test |
| `mna.py` | fast linear AC solver for that circuit (validated against ngspice to 0.1 dB) |
| `study.py`, `fit.py`, `opt.py` | first studies: op-amp table, C6 / Cp tweaks, search |
| `clone.py` | transistor-level LM4250 clone (AN-71 fig. 1) and its bench (GBW, slew, Iq) |
| `emu.py` | LM13700-style OTA emulator and clone vs reference in the circuit (small and large signal) |
| `bench2.py` | part-level bench vs Iset (1–20 µA) at 9 V and 18 V |
| `module.py` | low-voltage op-amp module (LDO window) |
| `compare_all.py` | the nine-candidate comparison and ranking |
| `lt_compare.py` | the same netlists in LTspice (Mac batch) |

Environment: `LM_VS=9` or `18` selects the supply (R7 stays 1M5 → Iset = (VS − 0.5) / 1.5 MΩ). ngspice must be on the PATH.

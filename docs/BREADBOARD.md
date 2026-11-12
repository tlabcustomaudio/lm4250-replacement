# Breadboard guide (9 V, Stingray-style preamp pedal (V3))

General rules for every variant
* The chip goes on the breadboard; a **DIP-8 plug** (a DIP-8 header/IC pins, or a DIP-8 plug cable) goes into the pedal's U1 socket. Pedal pins: 2 IN−, 3 IN+, 4 GND, 6 OUT, 7 +9 V, 1/5 offset (not used), 8 ISET.
* Measure first, insert later: check every supply rail on the breadboard **before** plugging in the active parts.
* 100 nF across the supply at each IC, leads short, input nodes away from the output/Cc wires. A breadboard adds ~3–10 pF of stray capacitance: expect Cc/C6 values to need tuning, and use the breadboard for function and first measurements, not as the final result.
* Pedal side per variant: **remove R7** for every variant except the discrete clone (the clone's pin 8 uses the pedal's R7 1M5 like the real chip).

## 1. TL071 (simplest)
TL071 in the socket; remove R7; C6 120 pF → 82 pF.

## 2. LM308
Remove R7. **100 pF (C0G) between pins 1 and 8**, wired at the socket. Try 150 pF afterwards. Pinout: 1 and 8 compensation, 2 −, 3 +, 4 V−, 6 out, 7 V+.

## 3. TLC271CP
Remove R7. **Pin 8 wired to pin 3** (4.5 V = VDD/2: medium bias). C6 stays 120 pF. (Max 16 V.)

## 4. LM13700 OTA emulator (≈5 mA; the HGSemi datasheet recommends ≥ 9.5 V single supply: check on a bench supply)
Chips: LM13700N (DIP-16), TL072, TL071. Parts: 2 × 12k, 39k, 390k, 2 × 100k, 180 pF C0G, 47M, 100 Ω, 100 nF ×4, 10 µF.
* Reference: 2 × 100k from +9 V to GND, 100 nF across the lower one → mid-supply **REF**.
* TL072 A = follower from plug pin 3 (IN+); TL072 B = follower from plug pin 2 (IN−).
* TL072 A out → 12k → node **dp**; TL072 B out → 12k → node **dn**; **39k between dp and dn**.
* LM13700 (amplifier A): pin 4 (Input −) = **dp**, pin 3 (Input +) = **dn** (swapped: the integrator inverts); pin 1 (Amp bias) → 390k to +9 V; pin 2 open; pin 6 = GND; pin 11 = +9 V; pin 5 (Output) = node **s**; everything else open.
* TL071 integrator: pin 2 = s; 180 pF and 47M both from pin 6 to pin 2; pin 3 = REF; supply pins 7/4. TL071 pin 6 → 100 Ω → plug pin 6.
* Checks: ≈ 20 µA into pin 1 (7.8 V across 390k); REF = 4.5 V; with the pedal's input shorted the output sits at REF.

## 5. OPA333 module (LDO window; the op-amp never sees 9 V)
Parts: OPA333 on a SOT-23-5/SOIC-8 → DIP breakout, LDO 5 V with a high input range (LP2950-5.0 TO-92, 30 V, or MCP1703A-5002), 78k, 22k, 10 µF, 1 µF, 100 nF.
* Divider **78k from +9 V to node VM, 22k from VM to GND**, 10 µF VM→GND: VM ≈ 2.0 V.
* LDO: **its GND pin on VM**, input = +9 V, output = **VREG**; 1 µF VREG→VM. VREG − VM must read 5.0 V.
* **Check VREG − VM = 5.0 V with a multimeter before inserting the OPA333.**
* OPA333: V+ = VREG, V− = VM, inputs/output to plug pins 3/2/6; 100 nF between VREG and VM. C6 stays 120 pF; remove R7.
* Output swing is limited to ±2.5 V around 4.5 V; lower input levels than with the real chip.

## 6. Discrete clone (18 transistors)
THT equivalents: **BC547B** (NPN) and **BC557B** (PNP) — check each maker's TO-92 pin order (ON: E-B-C; NXP: C-B-E) and verify with a multimeter. Select Q101/Q102 and Q103/Q104 as pairs (same hFE and Vbe within a few %) with a multimeter/transistor tester.
Clone parts are numbered **AN-71 number + 100** (Q101…Q118, R101…R117, C101) so they never clash with the pedal's own R7, C6… Resistors 1 % (E96), Cc (C101) **39 pF C0G** (the original 30 pF; tune 36–43 pF), R7 stays on the pedal PCB (1M5, pin 8 → GND).

| Q | Type | C | B | E |
|---|---|---|---|---|
| Q109 | PNP BC557B | ISET (DIP pin 8 → R7 on the pedal PCB) | ISET (DIP pin 8 → R7 on the pedal PCB) | e9 |
| Q110 | PNP BC557B | TAIL | ISET (DIP pin 8 → R7 on the pedal PCB) | e10 |
| Q111 | PNP BC557B | E | ISET (DIP pin 8 → R7 on the pedal PCB) | e11 |
| Q112 | PNP BC557B | S12 | ISET (DIP pin 8 → R7 on the pedal PCB) | e12 |
| Q101 | PNP BC557B | D1 | IN− (DIP pin 2) | e1 |
| Q102 | PNP BC557B | D2 | IN+ (DIP pin 3) | e2 |
| Q103 | NPN BC547B | D1 | D1 | NULL5 (DIP pin 5) |
| Q104 | NPN BC547B | D2 | D1 | NULL1 (DIP pin 1) |
| Q105 | PNP BC557B | V− (GND) | D2 | E |
| Q106 | NPN BC547B | E | E | G |
| Q107 | NPN BC547B | G | D1 | e7 |
| Q108 | NPN BC547B | H | G | V− (GND) |
| Q113 | NPN BC547B | S12 | S12 | M |
| Q114 | NPN BC547B | M | M | H |
| Q115 | NPN BC547B | A (V+ via R108) | S12 | X1 |
| Q118 | PNP BC557B | V− (GND) | H | X4 |

| R/C | Value | pin 1 | pin 2 |
|---|---|---|---|
| R108 | 100 | V+ (+9 V) | A (V+ via R108) |
| R109 | 4.99k | A (V+ via R108) | e9 |
| R110 | 6.04k | A (V+ via R108) | e10 |
| R111 | 4.99k | A (V+ via R108) | e11 |
| R112 | 2.49k | V+ (+9 V) | e12 |
| R101 | 10k | TAIL | e1 |
| R102 | 10k | TAIL | e2 |
| R103 | 4.99k | NULL5 (DIP pin 5) | V− (GND) |
| R104 | 4.99k | NULL1 (DIP pin 1) | V− (GND) |
| R107 | 10k | e7 | V− (GND) |
| C101 (Cc) | 39 pF (C0G) | D2 | H |
| R116 | 49.9 | X1 | X2 |
| R115 | 100 | X2 | O1 |
| R117 | 100 | X4 | X3 |
| R114 | 49.9 | X3 | O1 |
| R113 | 100 | O1 | OUT (DIP pin 6) |

(The schematic with the same nets is `kicad/` → `LM4250_CLONE.kicad_sch`; ISET, D1 and A are the labelled bias rails.)

DC checks with the pedal unplugged and the clone wired as a follower at 4.5 V (from the simulation): Q10 tail ≈ 5.04 V, E ≈ 1.03 V, G ≈ 0.53 V, H ≈ 4.0 V, S12 ≈ 5.1 V; supply current ≈ 70 µA at 9 V with R7 = 1M5 (measure with a 1 kΩ in series: ≈ 70 mV).
AC checks: gain ×10 non-inverting, −3 dB at ≈ 20 kHz; 1 V step follower slew ≈ 0.11 V/µs.

## Suggested order
TL071 → LM308 → TLC271 → LM13700 → OPA333 module → clone. Same control settings and the same DI bass track through the test station for each (sweep at RV1 max, 10 kHz burst at RV1 max).

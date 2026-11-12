# Stingray-style preamp pedal (V3, 9 V): replacing the LM4250 — what to change, per variant

Circuit facts (netlist of `MM.kicad_sch` V3): U1 is a DIP-8 socket, pins 2 (−), 3 (+, at Vdc = 4.5 V), 4 (GND), 6 (out), 7 (+9 V).
R7 1M5 goes from pin 8 to GND (sets the LM4250's Iset = 5.7 µA). C6 120 pF goes from pin 2 to the output (pin 6). Pins 1 and 5 are not connected.
Simulated 9 V worst case = level error vs the LM4250 reference with RV1 (treble) at max; everywhere else < 0.6 dB. Models are simplified: the bench decides.

## A. TL071 (have it)
* Remove R7 (pin 8 is not connected on a TL071).
* C6: 120 pF → **82 pF**.
* Expected: 2.3–2.8 dB error, no slew distortion (it is much faster than the LM4250).

## B. LM308 (maybe in the drawer)
* Pinout: 1 and 8 = compensation, 2 −, 3 +, 4 V−, 5 NC, 6 out, 7 V+.
* Remove R7. Solder a **compensation capacitor between pins 1 and 8** (C0G/film, wired under the socket or on a stacked socket): start with **100 pF**; also try 150 pF.
* C6 stays 120 pF.
* Expected: 100 pF → 1.2 dB (GBW ~300 kHz, slew ~0.09 V/µs); 150 pF → 0.6 dB (GBW ~200 kHz but slew only ~0.06 V/µs, a bit less than the LM4250's 0.10).
* Assumption to check against the LM308 datasheet: unity-gain 1 MHz / slew 0.3 V/µs with 30 pF, both ∝ 1/Ccomp. Old part, beware of fakes.

## C. TLC271CP (to buy; DIP-8, max 16 V — fine at 9 V, not at 18 V)
* Pinout: 1/5 offset, 2 −, 3 +, 4 GND, 6 out, 7 VDD, **8 bias select**.
* Remove R7. **Wire pin 8 to pin 3** (pin 3 sits at 4.5 V = VDD/2 → medium bias, GBW ≈ 0.5 MHz, slew ≈ 0.4 V/µs). Do the wire under the socket / on a stacked socket.
* C6 stays 120 pF.
* Expected: 2.2 dB. (Pin 8 to GND = high bias, 3.2 dB; pin 8 to V+ = low bias, 7.6 dB: not recommended.)

## D. LM13700 OTA emulator (lab build, ~5 mA: bench only)
Idea: input buffers → OTA (gm·tanh limit = slew) → inverting integrator. DIP-8 plug on the pedal socket, remove R7 (pin 8 unused).
Parts: LM13700N, TL072 (two input buffers), TL071 (integrator), 2× 12k, 39k, 390k, 2× 100k, 180 pF C0G, 47 MΩ, 100 nF ×4, 100 Ω.
* Supply: pin 7 (+9 V) / pin 4 (GND) of the plug. NOTE: the HGSemi LM13700 datasheet recommends ≥ 9.5 V single supply; at 9 V it may still work, test it on a bench supply and watch for battery sag.
* Buffers (TL072 A/B, unity-gain followers): plug pin 3 (IN+) → buffer A; plug pin 2 (IN−) → buffer B.
* Differential divider: buffer A out → 12k → node **dp**; buffer B out → 12k → node **dn**; **39k between dp and dn** (a = 0.62 → linear range ≈ 84 mV like the LM4250).
* LM13700 (DIP-16, amplifier A): **pin 4 (Input −) = dp, pin 3 (Input +) = dn** (swapped on purpose: the integrator inverts), pin 1 (Amp bias) → **390k** to +9 V (Iabc ≈ 20 µA: the pin sits two diode drops above V−; measure the 20 µA and adjust), pin 2 (diode bias) open, pin 6 (V−) = GND, pin 11 (V+) = +9 V, pin 5 (Output) = summing node **s**. Unused: pins 7/8 (buffer A), amplifier B (leave open).
* Integrator (TL071): pin 2 (−) = s; **180 pF from pin 6 (out) to pin 2** (+ 47 MΩ across it); pin 3 (+) = mid-supply reference (2× 100k from +9 V to GND, 100 nF to GND).
* TL071 out (pin 6) → 100 Ω → plug pin 6.
* 100 nF across the supply of every IC.
* Expected (behavioural sim): 1.4 dB. GBW = 19.2·a·Iabc / (2π·180 pF) ≈ 200 kHz, slew = Iabc / C ≈ 0.11 V/µs. The TL071 integrator limits the output swing to ~1.5–7.5 V.
* Tune Iabc for the bench: closed-loop gain ×10, −3 dB at ~20 kHz ↔ GBW 200 kHz.

## NOT to buy
* OPA333, MCP6061, OPA391: supply 5.5–6 V maximum, they die at 9 V.

## How to compare them
Same settings and the same DI bass track through the test station for each variant: RV1 max frequency response (sweep), 10 kHz burst at RV1 max (slew distortion), and the real LM4250 if you ever find one. Order of tests: TL071 → LM308 → LM13700 → TLC271.

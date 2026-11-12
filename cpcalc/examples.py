"""Ready-made cases: the spec demonstrations D1-D12 plus a few new ones.
Each example is a plain case dictionary, the same format the UI and the
workbook produce. Values printed in the spec are entered with the spec as
source; everything else comes from the built-in database."""
import copy

FIG1 = "spec v3 Fig. 1 (illustrative values)"
SEC361 = "spec v3 Sec. 3.6.1 (illustrative value)"


def val(component, key, value, unit, state="", T=None, kind="illustrative", source=FIG1):
    return {"component": component, "key": key, "value": value, "unit": unit, "state": state,
            "T_min": T, "T_max": T, "kind": kind, "source": source}


def phase(name, state, substance, amount, role="continuous", method="auto"):
    return {"name": name, "state": state, "substance": substance, "amount": amount, "role": role, "method": method}


def d3(phi=0.02, T=298.15):
    return {"name": "D3 Al2O3 in water, %g vol%%" % (100 * phi), "T": T, "P": 101325.0, "quantity": "both", "basis": "volume",
            "phases": [phase("base fluid", "liquid", "water", 1 - phi), phase("particles", "solid", "Al2O3", phi, "dispersed")],
            "data": [val("water", "cp", 4182, "J/kg/K", "liquid", 298.15), val("water", "rho", 997, "kg/m3", "liquid", 298.15),
                     val("water", "alpha_V", 2.5729e-4, "1/K", "liquid", 298.15, "estimated",
                         "CoolProp 8.0.0, quoted in spec v3 Sec. 3.6.1 [R]"),
                     val("water", "kappa_T", 4.5246e-10, "1/Pa", "liquid", 298.15, "estimated",
                         "CoolProp 8.0.0, quoted in spec v3 Sec. 3.6.1 [R]"),
                     val("Al2O3", "cp", 765, "J/kg/K", "solid", 298.15), val("Al2O3", "rho", 3970, "kg/m3", "solid", 298.15),
                     val("Al2O3", "alpha_V", 2.2e-5, "1/K", "solid", 298.15, source=SEC361),
                     val("Al2O3", "kappa_T", 4.0e-12, "1/Pa", "solid", 298.15, source=SEC361)]}


NRTL_ILLUSTRATIVE = [
    {"i": "ethanol", "j": "water", "key": "nrtl_b", "value": 300.0, "kind": "illustrative",
     "source": "spec v3 Sec. 3.5 illustrative NRTL (tau12 = 300/T), not fitted ethanol-water values"},
    {"i": "water", "j": "ethanol", "key": "nrtl_b", "value": 800.0, "kind": "illustrative",
     "source": "spec v3 Sec. 3.5 illustrative NRTL (tau21 = 800/T), not fitted ethanol-water values"},
    {"i": "ethanol", "j": "water", "key": "nrtl_alpha", "value": 0.3, "kind": "illustrative",
     "source": "spec v3 Sec. 3.5 illustrative NRTL (alpha = 0.3)"}]


def build():
    ex = {}
    ex["D1 hexane + heptane (ideal liquid mixture)"] = {
        "name": "D1 n-hexane/n-heptane x1 = 0.5", "T": 298.15, "P": 101325.0, "quantity": "both", "basis": "mass",
        "phases": [phase("liquid", "liquid", "hc", 1.0)],
        "mixtures": {"hc": {"basis": "mole", "model": "ideal", "components": {"n-hexane": 0.5, "n-heptane": 0.5}}}}
    ex["D2 ethanol + water, NRTL (illustrative parameters)"] = {
        "name": "D2 ethanol/water x1 = 0.5, illustrative NRTL", "T": 298.15, "P": 101325.0, "quantity": "both", "basis": "mass",
        "phases": [phase("solution", "liquid", "ethanol-water", 1.0)],
        "mixtures": {"ethanol-water": {"basis": "mole", "model": "auto", "components": {"ethanol": 0.5, "water": 0.5}}},
        "pairs": copy.deepcopy(NRTL_ILLUSTRATIVE),
        "sweep": {"variable": "x", "start": 0.0, "stop": 1.0, "n": 11, "target": "ethanol-water"}}
    ex["D3 Al2O3 in water, 2 vol% (spec Fig. 1 values)"] = dict(
        d3(0.02), sweep={"variable": "phi", "start": 0.0, "stop": 0.10, "n": 11, "target": "particles"})
    ex["D4 Al2O3 particles: JANAF c_p curve at 310 K"] = {
        "name": "D4 alpha-Al2O3 at 310 K", "T": 310.0, "P": 101325.0, "quantity": "cp", "basis": "mass",
        "phases": [phase("particles", "solid", "Al2O3", 1.0)],
        "sweep": {"variable": "T", "start": 100.0, "stop": 500.0, "n": 9, "target": ""}}
    ex["D5 oil-in-water emulsion, 10 vol% dodecane (database only)"] = {
        "name": "D5 10 vol% n-dodecane in water", "T": 298.15, "P": 101325.0, "quantity": "both", "basis": "volume",
        "phases": [phase("water", "liquid", "water", 0.9), phase("oil drops", "liquid", "n-dodecane", 0.1, "dispersed")],
        "sweep": {"variable": "T", "start": 280.0, "stop": 360.0, "n": 9, "target": ""}}
    ex["D6 hybrid nanofluid: EG/water + Al2O3 + Cu at 320 K"] = {
        "name": "D6 EG/water 20/80 wt% + 3 vol% Al2O3 + 1 vol% Cu", "T": 320.0, "P": 101325.0, "quantity": "both",
        "basis": "volume",
        "phases": [phase("base fluid", "liquid", "coolant", 0.96), phase("alumina", "solid", "Al2O3", 0.03, "dispersed"),
                   phase("copper", "solid", "Cu", 0.01, "dispersed")],
        "mixtures": {"coolant": {"basis": "mass", "model": "ideal", "components": {"ethylene glycol": 0.2, "water": 0.8}}}}
    ex["D7 benzene vapour 400 K, 1 bar (Peng-Robinson)"] = {
        "name": "D7 benzene gas", "T": 400.0, "P": 1.0e5, "quantity": "both", "basis": "mass",
        "phases": [phase("vapour", "gas", "benzene", 1.0, method="Peng-Robinson")]}
    ex["D8 methane + ethane gas at 5 bar"] = {
        "name": "D8 methane/ethane x = 0.5, 5 bar", "T": 300.0, "P": 5.0e5, "quantity": "both", "basis": "mass",
        "phases": [phase("gas", "gas", "natural gas", 1.0)],
        "mixtures": {"natural gas": {"basis": "mole", "model": "Peng-Robinson", "components": {"methane": 0.5, "ethane": 0.5}}}}
    ex["D9 copper: JANAF c_p; c_v by identity or Debye, 100-500 K"] = {
        "name": "D9 Cu solid", "T": 298.15, "P": 101325.0, "quantity": "both", "basis": "mass",
        "phases": [phase("copper", "solid", "Cu", 1.0)],
        "sweep": {"variable": "T", "start": 100.0, "stop": 500.0, "n": 9, "target": ""}}
    ex["D10 missing data: unknown particles"] = {
        "name": "D10 water + 'my particles' with no data", "T": 298.15, "P": 101325.0, "quantity": "both", "basis": "volume",
        "phases": [phase("base fluid", "liquid", "water", 0.95), phase("particles", "solid", "my particles", 0.05, "dispersed")]}
    ex["D11 water above its boiling point (out of range)"] = {
        "name": "D11 liquid water at 380 K", "T": 380.0, "P": 101325.0, "quantity": "both", "basis": "mass",
        "phases": [phase("water", "liquid", "water", 1.0)]}
    ex["New: propanol/water (30 vol%) + 5 vol% ZnO, 280-340 K"] = {
        "name": "propanol/water + ZnO", "T": 320.0, "P": 101325.0, "quantity": "cp", "basis": "volume",
        "phases": [phase("liquid", "liquid", "propanol-water", 0.95), phase("zinc oxide", "solid", "ZnO", 0.05, "dispersed")],
        "mixtures": {"propanol-water": {"basis": "volume", "model": "ideal", "components": {"1-propanol": 0.3, "water": 0.7}}},
        "sweep": {"variable": "T", "start": 280.0, "stop": 340.0, "n": 7, "target": ""}}
    ex["New: 2 vol% Al2O3 nanofluid, 280-350 K (database only)"] = {
        "name": "2 vol% Al2O3 in water vs T", "T": 300.0, "P": 101325.0, "quantity": "both", "basis": "volume",
        "phases": [phase("base fluid", "liquid", "water", 0.98), phase("particles", "solid", "Al2O3", 0.02, "dispersed")],
        "sweep": {"variable": "T", "start": 280.0, "stop": 350.0, "n": 8, "target": ""}}
    ex["Blank"] = {"name": "my case", "T": 298.15, "P": 101325.0, "quantity": "both", "basis": "volume",
                   "phases": [phase("base fluid", "liquid", "water", 1.0)]}
    return ex


EXAMPLES = build()


def get(name):
    return copy.deepcopy(EXAMPLES[name])

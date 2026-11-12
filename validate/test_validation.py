"""Independent validation against CoolProp (spec Sec. 9.4). SKIPPED when CoolProp is not installed.
Acceptance is fidelity to the spec's reference computations; model deviations are tabulated in
validate/error_table.txt, not judged."""
import os
import sys

import pytest

CP = pytest.importorskip("CoolProp.CoolProp", reason="CoolProp not installed", exc_type=ImportError)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cpcalc import pure, run_case                    # noqa: E402
from cpcalc.examples import get                      # noqa: E402

TABLE = []
NAMES = {"water": "Water", "ethanol": "Ethanol", "n-hexane": "n-Hexane", "benzene": "Benzene"}


def crit(n):
    return CP.PropsSI("Tcrit", n), CP.PropsSI("pcrit", n), CP.PropsSI("acentric", n)


@pytest.mark.parametrize("cid,ref", [("n-hexane", (187.8, 159.8)), ("benzene", (117.9, 94.6)),
                                     ("ethanol", (140.9, 107.5)), ("water", (81.2, 58.9))])
def test_val01_table3_pr_liquids(cid, ref):
    n = NAMES[cid]
    Tc, Pc, om = crit(n)
    m = 0.37464 + 1.54226 * om - 0.26992 * om ** 2 if cid == "ethanol" else None   # spec used PR76 for ethanol
    p = pure.pr_parameters(Tc, Pc, om, 298.15, m=m)
    st = pure.pr_state(298.15, 101325.0, p["a"], p["b"], p["da"], p["d2a"],
                       CP.PropsSI("CP0MOLAR", "T", 298.15, "P", 1e5, n), "liquid")
    assert st["Cp"] == pytest.approx(ref[0], rel=5e-3) and st["Cv"] == pytest.approx(ref[1], rel=5e-3)
    TABLE.append(("VAL-01", "%s liquid PR C_p" % cid, st["Cp"], CP.PropsSI("CPMOLAR", "T", 298.15, "P", 101325.0, n)))
    TABLE.append(("VAL-01", "%s liquid PR C_v" % cid, st["Cv"], CP.PropsSI("CVMOLAR", "T", 298.15, "P", 101325.0, n)))


def test_val02_benzene_gas():
    c = get([k for k in __import__("cpcalc.examples").examples.EXAMPLES if k.startswith("D7")][0])
    ref = CP.PropsSI("CPMOLAR", "T", 400.0, "P", 1e5, "Benzene"), CP.PropsSI("CVMOLAR", "T", 400.0, "P", 1e5, "Benzene")
    for method in ("ideal gas", "Peng-Robinson"):
        c["phases"][0]["method"] = method
        r = run_case(c)
        TABLE.append(("VAL-02", "benzene gas 400 K %s C_p" % method, r["molar"]["Cp"], ref[0]))
        TABLE.append(("VAL-02", "benzene gas 400 K %s C_v" % method, r["molar"]["Cv"], ref[1]))
        assert abs(r["molar"]["Cp"] / ref[0] - 1) < 0.02


@pytest.mark.parametrize("P,dcp,dcv", [(5e5, -0.20, -0.35), (10e5, -0.46, -0.75)])
def test_val05_methane_ethane(P, dcp, dcv):
    AS = CP.AbstractState("HEOS", "Methane&Ethane")
    AS.set_mole_fractions([0.5, 0.5])
    AS.update(CP.PT_INPUTS, P, 300.0)
    c = get([k for k in __import__("cpcalc.examples").examples.EXAMPLES if k.startswith("D8")][0])
    c["P"] = P
    r = run_case(c)
    TABLE.append(("VAL-05", "CH4/C2H6 %g bar C_p" % (P / 1e5), r["molar"]["Cp"], AS.cpmolar()))
    assert 100 * (r["molar"]["Cp"] / AS.cpmolar() - 1) == pytest.approx(dcp, abs=0.02)
    assert 100 * (r["molar"]["Cv"] / AS.cvmolar() - 1) == pytest.approx(dcv, abs=0.02)


@pytest.mark.parametrize("cid", ["water", "ethanol", "n-hexane", "benzene", "n-dodecane", "toluene"])
@pytest.mark.parametrize("T", [283.37, 301.11, 322.73, 337.9])
def test_val07_database_data_route_vs_coolprop(cid, T):
    """c_p and c_v from the database curves (interpolated) + the identity, against CoolProp at off-grid T."""
    name = {"n-dodecane": "n-Dodecane", "toluene": "Toluene"}.get(cid, NAMES.get(cid))
    if T > CP.PropsSI("T", "P", 101325.0, "Q", 0, name) - 1:
        pytest.skip("above the normal boiling point")
    r = run_case({"T": T, "P": 101325.0, "quantity": "both", "basis": "mass",
                  "phases": [{"name": "l", "state": "liquid", "substance": cid, "amount": 1.0}]})
    cp, cv = r["results"]["cp_app"]["value"], r["results"]["cv_app"]["value"]
    ref_cp = CP.PropsSI("CPMASS", "T", T, "P", 101325.0, name)
    ref_cv = CP.PropsSI("CVMASS", "T", T, "P", 101325.0, name)
    assert cp == pytest.approx(ref_cp, rel=1e-3) and cv == pytest.approx(ref_cv, rel=2e-3)
    if cid == "water":
        TABLE.append(("VAL-07", "water %.2f K c_v database route [J/kg/K]" % T, cv, ref_cv))


def test_tc17_water_cv_reference_values():
    for T, ref in [(280.0, 75.661), (298.15, 74.539), (320.0, 72.806), (350.0, 70.068)]:
        r = run_case({"T": T, "P": 101325.0, "quantity": "cv", "basis": "mass",
                      "phases": [{"name": "w", "state": "liquid", "substance": "water", "amount": 1.0}]})
        assert r["molar"]["Cv"] == pytest.approx(ref, rel=2e-4)


def teardown_module(module):
    if TABLE:
        with open(os.path.join(os.path.dirname(__file__), "error_table.txt"), "w") as fh:
            fh.write("Model vs CoolProp %s (acceptance is fidelity to the spec, not small error)\n" % __import__("CoolProp").__version__)
            fh.write("%-7s %-44s %12s %12s %8s\n" % ("test", "quantity", "model", "CoolProp", "dev %"))
            for t, q, m, ref in TABLE:
                fh.write("%-7s %-44s %12.4f %12.4f %+8.2f\n" % (t, q[:44], m, ref, 100 * (m / ref - 1)))

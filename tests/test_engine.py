"""Software tests: units, data lookup, fractions, mixtures, errors, warnings, status."""
import copy

import pytest

from conftest import two_phase
from cpcalc import run_case, CalcError
from cpcalc.database import load_database
from cpcalc.examples import get
from cpcalc.properties import interpolate, new_context, find
from cpcalc.units import to_si
from cpcalc.engine import check_case

DB = load_database()


def codes(res):
    return {w["code"] for w in res["warnings"]}


def water(T=298.15, data=None, quantity="both"):
    return {"T": T, "P": 101325.0, "quantity": quantity, "basis": "mass",
            "phases": [{"name": "w", "state": "liquid", "substance": "water", "amount": 1.0}], "data": data or []}


# ---------------------------------------------------------------- units
def test_unit_factors():
    assert to_si("cp", 4.2, "kJ/kg/K") == 4200.0
    assert to_si("rho", 1.0, "g/cm3") == 1000.0
    assert to_si("Pc", 2.0, "bar") == 2e5
    assert to_si("kappa_T", 1.0, "1/GPa") == 1e-9
    assert to_si("cp", 75.3, "J/mol/K", M=0.018015) == pytest.approx(75.3 / 0.018015)
    assert to_si("Tc", 25.0, "C") == pytest.approx(298.15)
    for bad in (("cp", 1.0, "kg/m3", None), ("cp", 1.0, "J/mol/K", None)):
        with pytest.raises(CalcError):
            to_si(*bad)


def test_curve_is_never_extrapolated():
    pts = [[100.0, 1.0], [200.0, 3.0]]
    assert interpolate(pts, 150.0) == 2.0
    assert interpolate(pts, 200.03) == 3.0           # within 0.05 K of the end
    assert interpolate(pts, 250.0) is None


# ---------------------------------------------------------------- where numbers come from
def test_database_fills_blanks_and_user_wins():
    r = run_case(water())
    assert r["results"]["cp_app"]["value"] == pytest.approx(4181.3, abs=0.05)
    assert all(p["route"].startswith("database") for p in r["provenance"])
    r = run_case(water(data=[{"component": "Water", "key": "cp", "value": 4100.0, "unit": "J/kg/K", "kind": "experimental",
                              "source": "t", "T_min": 290, "T_max": 300}]))
    assert r["results"]["cp_app"]["value"] == 4100.0
    assert "A09" not in codes(r)                     # 2 % difference: no warning
    r = run_case(water(data=[{"component": "water", "key": "cp", "value": 4500.0, "unit": "J/kg/K", "kind": "experimental",
                              "source": "t", "T_min": 290, "T_max": 300}]))
    assert "A09" in codes(r)


def test_user_value_outside_its_range_is_skipped():
    d = [{"component": "water", "key": "cp", "value": 4100.0, "unit": "J/kg/K", "T_min": 298.15, "T_max": 298.15,
          "kind": "experimental", "source": "t"}]
    r = run_case(water(320.0, d))
    assert r["results"]["cp_app"]["value"] != 4100.0          # database curve used instead


def test_value_without_range_is_an_assumption():
    d = [{"component": "water", "key": "cp", "value": 4100.0, "unit": "J/kg/K", "kind": "experimental", "source": "t"}]
    r = run_case(water(320.0, d))
    assert r["results"]["cp_app"]["value"] == 4100.0
    assert any(a["name"] == "no_T_range" for a in r["assumptions"]["used"])
    assert r["status"] == "calculated under assumptions"


def test_out_of_range_is_E04_with_phase_change_hint():
    r = run_case(water(380.0))
    p = r["problems"][0]
    assert p["code"] == "E04" and any("boils" in l for l in p["lines"])
    assert r["results"]["cp_app"]["value"] is None


def test_molar_value_needs_M():
    c = water(data=[{"component": "x", "key": "cp", "value": 100.0, "unit": "J/mol/K", "kind": "experimental", "source": "t"}])
    c["phases"][0]["substance"] = "x"
    c["quantity"] = "cp"
    r = run_case(c)
    assert r["status"] == "not calculable" and "molar mass" in " ".join(r["problems"][0]["lines"])
    c["data"].append({"component": "x", "key": "M", "value": 50.0, "unit": "g/mol", "kind": "experimental", "source": "t"})
    assert run_case(c)["results"]["cp_app"]["value"] == pytest.approx(2000.0)


def test_alpha_derived_from_a_density_curve():
    c = two_phase()
    c["data"] = [d for d in c["data"] if not (d["component"] == "fluid" and d["key"] in ("alpha_V", "rho"))]
    c["curves"] = [{"component": "fluid", "key": "rho", "state": "liquid", "unit": "kg/m3", "kind": "experimental",
                    "source": "t", "points": [[290.0, 1001.6], [300.0, 999.6], [310.0, 997.6]]}]
    r = run_case(c)
    rec = [p for p in r["provenance"] if p["key"] == "alpha_V" and p["comp"] == "fluid"][0]
    assert rec["route"] == "derived" and rec["kind"] == "derived"
    assert rec["value"] == pytest.approx(0.2 / (1001.6 - 0.2 * 8.15), rel=1e-9)


def test_names_aliases_and_cas_resolve():
    for name in ("Al2O3", "alumina", "1344-28-1"):
        c = get("D4 Al2O3 particles: JANAF c_p curve at 310 K")
        c.pop("sweep")
        c["phases"][0]["substance"] = name
        assert run_case(c)["results"]["cp_app"]["value"] == pytest.approx(795.233, abs=1e-3)


# ---------------------------------------------------------------- fractions and mixtures
@pytest.mark.parametrize("amounts", [[1.2, -0.2], [0.5, 0.4], ["x", 1.0]])
def test_bad_phase_fractions(amounts):
    c = two_phase()
    c["phases"][0]["amount"], c["phases"][1]["amount"] = amounts
    with pytest.raises(CalcError) as e:
        run_case(c)
    assert e.value.code == "E03"


def test_small_drift_renormalised():
    c = two_phase()
    c["phases"][0]["amount"] = 0.9805
    r = run_case(c)
    assert "A02" in codes(r) and sum(p["phi"] for p in r["phases"]) == pytest.approx(1, abs=1e-12)


def test_mixture_bases_agree():
    """The same hexane/heptane mixture given by mole, mass and volume fractions."""
    base = get("D1 hexane + heptane (ideal liquid mixture)")
    r_mole = run_case(base)
    ctx = new_context(check_case(base, DB), DB)
    M = {c: find(ctx, c, "M")["value"] for c in ("n-hexane", "n-heptane")}
    rho = {c: find(ctx, c, "rho", "liquid")["value"] for c in ("n-hexane", "n-heptane")}
    w = {c: 0.5 * M[c] / sum(0.5 * M[k] for k in M) for c in M}
    phi = {c: (w[c] / rho[c]) / sum(w[k] / rho[k] for k in w) for c in w}
    for basis, frac in (("mass", w), ("volume", phi)):
        c = copy.deepcopy(base)
        c["mixtures"]["hc"].update(basis=basis, components=frac)
        r = run_case(c)
        assert r["results"]["cp_app"]["value"] == pytest.approx(r_mole["results"]["cp_app"]["value"], rel=1e-12)
        assert r["results"]["cv_app"]["value"] == pytest.approx(r_mole["results"]["cv_app"]["value"], rel=1e-12)


def test_any_substance_works_with_enough_data():
    """A compound not in the database (here a made-up 'oil X') with user data."""
    c = two_phase()
    for d in c["data"]:
        if d["component"] == "fluid":
            d["component"] = "oil X"
    c["phases"][0]["substance"] = "oil X"
    assert run_case(c)["status"] == "calculated"


def test_auto_mixture_model_choice():
    c = get("D2 ethanol + water, NRTL (illustrative parameters)")
    c.pop("sweep")
    r = run_case(c)
    assert r["phases"][0]["method_cp"] == "NRTL"
    c["pairs"] = []
    r = run_case(c)
    assert r["phases"][0]["method_cp"] == "ideal"
    assert any(a["name"] == "ce_zero" for a in r["assumptions"]["used"])


def test_nrtl_needs_two_components_E06():
    c = get("D2 ethanol + water, NRTL (illustrative parameters)")
    c.pop("sweep")
    c["mixtures"]["ethanol-water"]["components"] = {"ethanol": 0.4, "water": 0.4, "methanol": 0.2}
    c["mixtures"]["ethanol-water"]["model"] = "NRTL"
    r = run_case(c)
    assert r["problems"][0]["code"] == "E06"


# ---------------------------------------------------------------- errors, warnings, status
def test_input_errors_are_reported_together():
    c = two_phase()
    c["T"] = -5
    c["data"][0]["unit"] = "kg/m3"
    c["optional_terms"] = ["interface"]
    with pytest.raises(CalcError) as e:
        run_case(c)
    assert {"E07", "E02", "E09"} <= {p["code"] for p in e.value.problems}


def test_missing_data_is_one_message_per_phase():
    r = run_case(get("D10 missing data: unknown particles"))
    assert len(r["problems"]) == 1
    p = r["problems"][0]
    assert p["code"] == "E01" and "data needs: cp" in p["lines"] and "Debye needs" in " ".join(p["lines"])
    assert "not in the database" in p["fix"]


def test_partly_calculable():
    c = two_phase()
    c["data"] = [d for d in c["data"] if d["key"] != "kappa_T"]
    r = run_case(c)
    assert r["status"] == "partly calculable"
    assert r["results"]["cp_app"]["status"] == "calculated" and r["results"]["cv_app"]["value"] is None


def test_status_rules():
    assert run_case(two_phase())["status"] == "calculated"
    r = run_case(two_phase(kind="illustrative"))
    assert r["status"] == "calculated under assumptions" and "A08" in codes(r)
    assert run_case(two_phase(kind="estimated"))["status"] == "calculated under assumptions"


def test_dispersed_fraction_warning_A03():
    assert "A03" in codes(run_case(two_phase(0.65)))
    c = two_phase(0.65)
    c["phi_warn"] = None
    assert "A03" not in codes(run_case(c))


def test_eos_warnings_and_root_errors():
    c = get("D7 benzene vapour 400 K, 1 bar (Peng-Robinson)")
    c["phases"][0]["state"] = "liquid"                      # vapour is stable at 400 K, 1 bar
    r = run_case(c)
    assert {"A05", "A11"} <= codes(r)
    c = get("D7 benzene vapour 400 K, 1 bar (Peng-Robinson)")
    c["T"] = 560.0
    assert "A04" in codes(run_case(c))
    c = get("D7 benzene vapour 400 K, 1 bar (Peng-Robinson)")
    c["phases"][0].update(substance="ethanol", state="liquid")
    c["T"] = 300.0
    assert {"A06", "A12"} <= codes(run_case(c))
    c = get("D7 benzene vapour 400 K, 1 bar (Peng-Robinson)")
    c["T"], c["P"] = 600.0, 1e5                              # above Tc at low P: one vapour-like root
    c["phases"][0]["state"] = "liquid"
    assert run_case(c)["problems"][0]["code"] == "E05"
    assert "A07" in codes(run_case(get("D8 methane + ethane gas at 5 bar")))


def test_unsupported_terms_E09():
    c = get("D3 Al2O3 in water, 2 vol% (spec Fig. 1 values)")
    c["optional_terms"] = ["latent heat"]
    with pytest.raises(CalcError) as e:
        run_case(c)
    assert e.value.code == "E09"


def test_zero_amount_phase_needs_no_data():
    c = two_phase()
    c["phases"].append({"name": "ghost", "state": "solid", "substance": "nothing known", "amount": 0.0})
    assert run_case(c)["results"]["cp_app"]["value"] == pytest.approx(run_case(two_phase())["results"]["cp_app"]["value"])

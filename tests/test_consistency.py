"""Thermodynamic consistency (spec Table 19): exact identities and limits, no external data."""
import copy
import math

import pytest

from conftest import two_phase
from cpcalc import pure, mixtures as mx, run_case
from cpcalc.constants import R
from cpcalc.database import load_database
from cpcalc.examples import get, d3

DB = load_database()


def crit(cid):
    vals = {r["key"]: r["value"] for r in DB["components"][cid]["records"] if r["key"] in ("Tc", "Pc", "omega")}
    return vals["Tc"], vals["Pc"], vals["omega"]


def test_tc01_cp_equals_cv_iff_alpha_zero():
    assert pure.cp_minus_cv(277.13, 1000.0, 0.0, 4.9e-10) == 0.0
    assert pure.cp_minus_cv(277.13, 1000.0, -3e-8, 4.9e-10) > 0.0


def test_tc02_ideal_gas_limit():
    Tc, Pc, om = crit("benzene")
    p = pure.pr_parameters(Tc, Pc, om, 400.0)
    st = pure.pr_state(400.0, 1e-3, p["a"], p["b"], p["da"], p["d2a"], 100.0, "vapour")
    assert abs(st["CpR"]) < 1e-6 and abs(st["Cv"] - (100.0 - R)) < 1e-6


def test_tc03_cvr_closed_form_vs_integral():
    from scipy.integrate import quad
    Tc, Pc, om = crit("water")
    T, v = 350.0, 1e-3
    p = pure.pr_parameters(Tc, Pc, om, T)
    numeric = T * quad(lambda vv: p["d2a"] / (vv * vv + 2 * p["b"] * vv - p["b"] ** 2), v, math.inf)[0]
    assert pure.cv_residual(T, v, p["b"], p["d2a"]) == pytest.approx(numeric, rel=1e-6)
    assert numeric == pytest.approx(1.012672, rel=1e-6)                    # spec [R]


def test_tc04_derivatives():
    Tc, Pc, om = crit("water")
    a = lambda T: pure.pr_parameters(Tc, Pc, om, T)["a"]
    p, h = pure.pr_parameters(Tc, Pc, om, 350.0), 0.1
    assert p["da"] == pytest.approx((a(350.1) - a(349.9)) / (2 * h), rel=1e-3)
    assert p["d2a"] == pytest.approx((a(350.1) - 2 * a(350.0) + a(349.9)) / h ** 2, rel=1e-3)
    assert p["da"] == pytest.approx(-1.355745e-3, rel=1e-5)


@pytest.mark.parametrize("T,P,root,ref", [(400.0, 1e5, "vapour", 0.683458), (298.15, 101325.0, "liquid", 36.34277)])
def test_tc05_cpr_is_dhr_dt(T, P, root, ref):
    Tc, Pc, om = crit("benzene")

    def hr(TT):
        p = pure.pr_parameters(Tc, Pc, om, TT)
        st = pure.pr_state(TT, P, p["a"], p["b"], p["da"], p["d2a"], 100.0, root)
        return pure.h_residual_over_RT(TT, st["Z"], st["A"], st["B"], p["a"], p["da"], p["b"]) * R * TT, st
    d = (hr(T + 1e-3)[0] - hr(T - 1e-3)[0]) / 2e-3
    assert hr(T)[1]["CpR"] == pytest.approx(d, rel=1e-6)
    assert hr(T)[1]["CpR"] == pytest.approx(ref, rel=1e-5)


@pytest.mark.parametrize("cid,T,ref", [("benzene", 298.15, 13.575), ("n-hexane", 298.15, 20.381), ("water", 373.15, 96.364)])
def test_tc07_saturation_and_root_switch(cid, T, ref):
    Tc, Pc, om = crit(cid)
    Ps = pure.saturation_pressure(Tc, Pc, om, T)
    assert Ps / 1000 == pytest.approx(ref, abs=1.5e-3)                      # spec Table 4
    p = pure.pr_parameters(Tc, Pc, om, T)
    below = pure.pr_state(T, 0.9 * Ps, p["a"], p["b"], p["da"], p["d2a"], 50.0, "stable")
    above = pure.pr_state(T, 1.1 * Ps, p["a"], p["b"], p["da"], p["d2a"], 50.0, "stable")
    assert below["label"].startswith("vapour") and above["label"].startswith("liquid")


def test_tc08_debye():
    th = 343.0
    assert pure.debye_cv(0.05 * th, th, 1) / pure.debye_low_T_limit(0.05 * th, th, 1) == pytest.approx(1, abs=1e-3)
    vals = [pure.debye_cv(r * th, th, 1) / (3 * R) for r in (0.05, 0.1, 0.2, 0.5, 1, 2, 5)]
    for got, ref in zip(vals, [0.0097, 0.0758, 0.369, 0.825, 0.9517, 0.9876, 0.9980]):
        assert got == pytest.approx(ref, abs=6e-4)
    assert all(b > a for a, b in zip(vals, vals[1:]))


def test_tc09_margules():
    assert mx.margules_he(0.5, 298.15, 100.0, 0.01) == pytest.approx(201.664, abs=1e-3)
    assert mx.margules_cpe(0.5, 298.15, 0.01) == pytest.approx(-0.020786, abs=1e-6)
    g = lambda T: mx.ge_margules(0.5, T, 0.3, 100.0, 0.01)
    assert mx.he_from_ge(g, 298.15) == pytest.approx(201.664, abs=1e-3)


def test_tc10_nrtl_against_sympy():
    p = {"a12": 0, "b12": 300.0, "e12": 0, "a21": 0, "b21": 800.0, "e21": 0, "alpha": 0.3}
    g = lambda T: mx.ge_nrtl(0.5, T, p)
    assert g(298.15) == pytest.approx(1557.72, abs=5e-3)
    assert mx.cpe_from_ge(g, 298.15) == pytest.approx(3.847818, rel=1e-5)
    sp = pytest.importorskip("sympy")
    T = sp.symbols("T")
    t12, t21 = 300 / T, 800 / T
    G12, G21 = sp.exp(-sp.Rational(3, 10) * t12), sp.exp(-sp.Rational(3, 10) * t21)
    ge = sp.Float(R) * T / 4 * (t21 * G21 / (sp.Rational(1, 2) + G21 / 2) + t12 * G12 / (sp.Rational(1, 2) + G12 / 2))
    assert mx.cpe_from_ge(g, 298.15) == pytest.approx(float((-T * sp.diff(ge, T, 2)).subs(T, 298.15)), rel=1e-5)


def test_tc11_gibbs_duhem():
    Cp = lambda x: 120.0 * x + 75.0 * (1 - x) + mx.margules_cpe(x, 298.15, 0.37)
    for x in (0.1, 0.5, 0.9):
        assert abs(mx.gibbs_duhem_residual(Cp, x, 1e-3)) < 1e-8


def test_tc12_invariants():
    ref = run_case(d3(0.02))
    cp0, cv0 = ref["results"]["cp_app"]["value"], ref["results"]["cv_app"]["value"]
    assert cp0 == pytest.approx(3925.1897, abs=1e-4) and cp0 - cv0 == pytest.approx(40.59795, rel=2e-5)
    c = d3(0.02)
    c["phases"].reverse()
    assert run_case(c)["results"]["cp_app"]["value"] == pytest.approx(cp0, rel=1e-12)
    c = d3(0.02)
    c["phases"][1]["amount"] = 0.01
    c["phases"].append(dict(c["phases"][1], name="particles 2"))
    r = run_case(c)
    assert r["results"]["cp_app"]["value"] == pytest.approx(cp0, rel=1e-10)
    assert r["results"]["cv_app"]["value"] == pytest.approx(cv0, rel=1e-10)


def test_tc13_cv_lower_bound_and_gap():
    r = run_case(d3(0.02))
    assert r["diagnostics"]["gap"] == pytest.approx(0.5489, abs=1e-4)
    assert r["diagnostics"]["gap"] == pytest.approx(r["diagnostics"]["gap_eq23"], rel=1e-9)
    assert run_case(d3(0.05))["diagnostics"]["gap"] == pytest.approx(1.2652, abs=1e-4)
    c = two_phase()
    for d in c["data"]:
        if d["component"] == "part" and d["key"] == "kappa_T":
            d["value"] = 2.0e-5 / (2.0e-4 / 5.0e-10)                    # same alpha/kappa in both phases
    r = run_case(c)
    assert r["results"]["cv_app"]["value"] == pytest.approx(r["diagnostics"]["sum_w_cv"], rel=1e-9)


def test_tc14_mass_and_volume_bases_agree():
    rv = run_case(two_phase(0.1))
    c = two_phase(0.1, basis="mass")
    for p in c["phases"]:
        p["amount"] = [q for q in rv["phases"] if q["name"] == p["name"]][0]["w"]
    rm = run_case(c)
    assert rm["results"]["cp_app"]["value"] == pytest.approx(rv["results"]["cp_app"]["value"], rel=1e-12)


def test_tc15_units_invariance():
    ref = run_case(d3(0.02))
    c = d3(0.02)
    for d in c["data"]:
        if d["key"] == "cp":
            d["value"], d["unit"] = d["value"] / 1000, "kJ/kg/K"
        if d["key"] == "rho":
            d["value"], d["unit"] = d["value"] / 1000, "g/cm3"
        if d["key"] == "kappa_T":
            d["value"], d["unit"] = d["value"] * 1e9, "1/GPa"
    r = run_case(c)
    for k in ("cp_app", "cv_app"):
        assert r["results"][k]["value"] == pytest.approx(ref["results"][k]["value"], rel=1e-12)


def test_limits_phi_to_zero_and_one():
    assert run_case(two_phase(0.0))["results"]["cp_app"]["value"] == pytest.approx(4000.0, rel=1e-14)
    assert run_case(two_phase(1.0))["results"]["cp_app"]["value"] == pytest.approx(800.0, rel=1e-14)

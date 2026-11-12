"""V3 additions: the NRTL helper, the Advanced section, the Save/open buttons and the theory pages."""
import math
import os
import re

import pytest

from cpcalc import mixtures as mx, theory, workbook, examples, database
from cpcalc.engine import run_case

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "cpcalc", "app.py")
ASSN = dict(a12=0.0, b12=3.17, e12=0.0, a21=0.0, b21=523.84, e21=0.0, alpha=0.30)     # tau = A/T, ethanol (1) + water (2)


# ------------------------------------------------------------------ helper and the equations printed on the theory pages
def test_nrtl_summary_matches_limits_of_ge():
    T = 298.15
    s = mx.nrtl_summary(ASSN, T)
    assert s["tau12"] == pytest.approx(3.17 / T) and s["tau21"] == pytest.approx(523.84 / T)
    g = lambda x1: mx.ge_nrtl(x1, T, ASSN) / (mx.R * T)
    h = 1e-7
    lng1 = g(1e-7) + (1 - 1e-7) * (g(1e-7 + h) - g(1e-7 - h)) / (2 * h)
    x = 1 - 1e-7
    lng2 = g(x) - x * (g(x + h) - g(x - h)) / (2 * h)
    assert math.log(s["gamma1_inf"]) == pytest.approx(lng1, abs=1e-5)
    assert math.log(s["gamma2_inf"]) == pytest.approx(lng2, abs=1e-5)


def test_nrtl_activity_coefficients_on_the_theory_page_are_consistent_with_ge():
    """ln gamma_i of page 7 = derivative of n G^E / RT with respect to n_i; and Gibbs-Duhem holds."""
    T, p = 310.0, dict(ASSN, a12=0.2, e12=0.01)

    def taus(T_):
        t12, t21 = mx.nrtl_tau(p["a12"], p["b12"], p["e12"], T_), mx.nrtl_tau(p["a21"], p["b21"], p["e21"], T_)
        return t12, t21, math.exp(-p["alpha"] * t12), math.exp(-p["alpha"] * t21)

    def lng(x1):
        x2 = 1 - x1
        t12, t21, G12, G21 = taus(T)
        l1 = x2 ** 2 * (t21 * (G21 / (x1 + x2 * G21)) ** 2 + t12 * G12 / (x2 + x1 * G12) ** 2)
        l2 = x1 ** 2 * (t12 * (G12 / (x2 + x1 * G12)) ** 2 + t21 * G21 / (x1 + x2 * G21) ** 2)
        return l1, l2

    def ng(n1, n2):            # n G^E / RT
        return (n1 + n2) * mx.ge_nrtl(n1 / (n1 + n2), T, p) / (mx.R * T)

    n1, n2, h = 0.4, 0.6, 1e-6
    d1 = (ng(n1 + h, n2) - ng(n1 - h, n2)) / (2 * h)
    d2 = (ng(n1, n2 + h) - ng(n1, n2 - h)) / (2 * h)
    l1, l2 = lng(0.4)
    assert l1 == pytest.approx(d1, abs=1e-6) and l2 == pytest.approx(d2, abs=1e-6)
    h = 1e-6                    # Gibbs-Duhem: x1 dln(g1)/dx1 + x2 dln(g2)/dx1 = 0
    a = [(u - v) / (2 * h) for u, v in zip(lng(0.4 + h), lng(0.4 - h))]
    assert 0.4 * a[0] + 0.6 * a[1] == pytest.approx(0.0, abs=1e-6)


def test_margules_formulas_on_the_theory_page():
    """H^E = G^E - T dG^E/dT and C_p^E = dH^E/dT for G^E/RT = x1 x2 (A + B/T + D ln T)."""
    A, B, D, x1, T, h = 0.3, 250.0, 0.4, 0.35, 300.0, 1e-3
    ge = lambda T_: mx.ge_margules(x1, T_, A, B, D)
    he = lambda T_: ge(T_) - T_ * (ge(T_ + h) - ge(T_ - h)) / (2 * h)
    assert he(T) == pytest.approx(mx.margules_he(x1, T, B, D), rel=1e-5)
    assert (he(T + h) - he(T - h)) / (2 * h) == pytest.approx(mx.margules_cpe(x1, T, D), rel=1e-4)


# ------------------------------------------------------------------ theory pages
def test_theory_pages_are_complete_and_numbered_in_order():
    for n, t in enumerate(theory.TOPICS):
        assert t["title"].startswith("%d. " % n), t["title"]
        assert t["text"] and t["code"] and isinstance(t["equations"], list)
        for eq, cap in t["equations"]:
            assert eq and cap
        if t.get("next"):
            assert re.search(r"[Pp]age", t["next"])
    titles = " ".join(t["title"] for t in theory.TOPICS)
    for word in ("NRTL", "Margules", "k_ij", "Peng-Robinson", "Debye", "Start here", "Symbols"):
        assert word in titles
    assert theory.TOPICS[0].get("diagram", "").lstrip().startswith("digraph")


# ------------------------------------------------------------------ web interface
@pytest.fixture
def app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception
    return at


def load_example(at, prefix):
    at.sidebar.selectbox[0].set_value([o for o in at.sidebar.selectbox[0].options if o.startswith(prefix)][0])
    at.sidebar.button[0].click()
    at.run()
    assert not at.exception


def pairs(at):
    return {(p["i"], p["j"], p["key"]): p["value"] for p in at.session_state["case"]["pairs"]}


def test_all_theory_pages_render(app):
    r = [x for x in app.radio if x.label == "Topic"][0]
    for opt in r.options:
        r.set_value(opt)
        app.run()
        assert not app.exception, opt


def test_sidebar_has_clear_save_open_and_add_compound_boxes(app):
    labels = [b.label for b in app.sidebar.button]
    assert labels[0] == "Load example"                               # existing tests rely on this order
    assert "Find in thermo" in labels and "Add as my own" in labels
    text = " ".join(m.value for m in app.sidebar.markdown)
    assert "Save / open a case" in text and "Add a compound" in text
    dl = [d.proto.label for d in app.get("download_button")]
    assert "Download this case (.xlsx)" in dl and "Download a blank template (.xlsx)" in dl


def test_advanced_nrtl_form_writes_the_pair_table_and_runs(app):
    load_example(app, "D2")                                           # ethanol + water, NRTL
    keyed = lambda k, tag: [w for w in app.number_input if w.key and w.key.startswith("adv_n_%s_%s_" % (k, tag))][0]
    for tag, A in (("12", 3.17), ("21", 523.84)):
        keyed("a", tag).set_value(0.0)
        keyed("b", tag).set_value(A)
        keyed("e", tag).set_value(0.0)
    [w for w in app.number_input if w.label.startswith("alpha")][0].set_value(0.30)
    [b for b in app.button if "Apply" in b.label][0].click()
    app.run()
    assert not app.exception
    got = pairs(app)
    assert got == {("ethanol", "water", "nrtl_alpha"): 0.30, ("ethanol", "water", "nrtl_b"): 3.17, ("water", "ethanol", "nrtl_b"): 523.84}
    assert app.session_state["case"]["mixtures"]["ethanol-water"]["model"] == "NRTL"
    assert any("gamma_ethanol = 5.857" in c.value for c in app.caption)
    # the number the app shows equals the engine run on the same case
    res = run_case(app.session_state["case"])
    cp = res["results"]["cp_app"]["value"]
    assert any(m.value == "%.6g" % cp for m in app.metric)
    assert cp != pytest.approx(3045.64, abs=1.0)           # different parameters than example D2 -> a different answer


def test_advanced_margules_form_always_writes_D(app):
    load_example(app, "D2")
    [r for r in app.radio if r.label == "Parameters for"][0].set_value("Margules")
    app.run()
    assert not app.exception
    [b for b in app.button if "Apply" in b.label][0].click()           # all zero: D must still be written
    app.run()
    assert not app.exception
    assert ("ethanol", "water", "marg_D") in pairs(app)
    assert app.session_state["case"]["mixtures"]["ethanol-water"]["model"] == "Margules"


def test_advanced_kij_form_for_a_gas_mixture(app):
    load_example(app, "D8")                                            # methane + ethane gas
    r = [x for x in app.radio if x.label == "Parameters for"][0]
    assert r.value == "Peng-Robinson k_ij"
    [w for w in app.number_input if w.label.startswith("k_ij")][0].set_value(0.01)
    [b for b in app.button if "Apply" in b.label][0].click()
    app.run()
    assert not app.exception
    assert list(pairs(app).values()) == [0.01] and list(pairs(app))[0][2] == "kij"


def test_advanced_nrtl_asks_for_two_components(app):
    load_example(app, "D8")
    # a three-component mixture must show the explanation instead of the form
    case = app.session_state["case"]
    only = next(iter(case["mixtures"]))
    case["mixtures"][only]["components"] = {"methane": 0.3, "ethane": 0.3, "propane": 0.4}
    app.session_state["v"] += 1                                       # make the tables reload from the case
    app.run()
    [r for r in app.radio if r.label == "Parameters for"][0].set_value("NRTL")
    app.run()
    assert not app.exception
    assert any("exactly two components" in i.value for i in app.info)


def test_blank_template_opens_again():
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        workbook.save_case(examples.get("Blank"), path, database.load_database())
        case = workbook.load_case(path)
    finally:
        os.remove(path)
    assert case["T"] == pytest.approx(298.15)

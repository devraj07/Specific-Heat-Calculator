"""Every example runs; spec [R] numbers are reproduced (relative tolerance 1e-3)."""
import pytest

from cpcalc import run_case, run_sweep
from cpcalc.examples import EXAMPLES, get

REL = 1e-3


def res(name, sweep=False):
    c = get(name)
    if not sweep:
        c.pop("sweep", None)
        return run_case(c)
    return run_sweep(c)


def find(prefix):
    return [n for n in EXAMPLES if n.startswith(prefix)][0]


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_every_example_runs(name):
    c = get(name)
    run_case(dict(c, sweep=None) if "sweep" in c else c)
    if c.get("sweep"):
        assert all(p["result"] or p["error"] for p in run_sweep(c)["points"])


def test_d1():
    r = res(find("D1"))
    ph = r["phases"][0]
    assert r["molar"]["Cp"] == pytest.approx(210.169, rel=REL)
    assert r["molar"]["Cp"] - r["molar"]["Cv"] == pytest.approx(45.553, rel=REL)
    assert r["molar"]["Cv"] == pytest.approx(164.615, rel=REL)
    assert ph["extra"]["sum_w_cv_i"] * ph["M"] == pytest.approx(164.594, rel=REL)


def test_d2():
    r = res(find("D2"))
    assert r["phases"][0]["extra"]["CpE"] == pytest.approx(3.847818, rel=1e-5)
    assert len(res(find("D2"), True)["points"]) == 11


def test_d3():
    r = res(find("D3"))
    assert r["phases"][1]["w"] == pytest.approx(0.07516, rel=REL)
    assert r["results"]["cp_app"]["value"] == pytest.approx(3925.19, rel=REL)
    assert r["results"]["cv_app"]["value"] == pytest.approx(3884.59, rel=REL)
    sw = res(find("D3"), True)
    diffs = {round(p["x"], 3): p["result"]["diagnostics"].get("volume_weighted_pct") for p in sw["points"]}
    for phi, ref in [(0.01, 2.4), (0.02, 4.8), (0.05, 11.7), (0.1, 22.5)]:
        assert diffs[phi] == pytest.approx(ref, abs=0.05)
    five = [p["result"] for p in sw["points"] if abs(p["x"] - 0.05) < 1e-9][0]
    assert five["results"]["cp_app"]["value"] == pytest.approx(3589.96, rel=REL)
    assert five["results"]["cv_app"]["value"] == pytest.approx(3553.48, rel=REL)


def test_d4_janaf_curve():
    c = get(find("D4"))
    c.pop("sweep")
    c["T"] = 298.15
    assert run_case(c)["results"]["cp_app"]["value"] == pytest.approx(774.95, abs=0.005)
    assert res(find("D4"))["results"]["cp_app"]["value"] == pytest.approx((79.416 + 16.67 * 0.1) / 0.1019612, rel=1e-4)
    c["T"] = 520.0
    assert run_case(c)["problems"][0]["code"] == "E04"


def test_d5_from_database_only():
    r = res(find("D5"))
    assert r["phases"][1]["w"] == pytest.approx(0.07673, rel=REL)
    assert r["rho_s"] == pytest.approx(971.92, rel=REL)
    assert r["results"]["cp_app"]["value"] == pytest.approx(4030.24, rel=REL)
    assert r["results"]["cp_app"]["value"] - r["results"]["cv_app"]["value"] == pytest.approx(66.264, rel=REL)
    assert r["diagnostics"]["sum_w_cv"] == pytest.approx(3959.46, rel=REL)
    assert r["status"] == "calculated"


def test_d6_hybrid_from_database():
    r = res(find("D6"))
    assert sum(p["w"] for p in r["phases"]) == pytest.approx(1, abs=1e-12)
    assert r["results"]["cv_app"]["value"] is not None


def test_d7_benzene():
    c = get(find("D7"))
    r = run_case(c)
    assert r["molar"]["Cp"] == pytest.approx(114.0, rel=REL) and r["molar"]["Cv"] == pytest.approx(105.1, rel=REL)
    assert r["phases"][0]["extra"]["Z"] == pytest.approx(0.9793, rel=1e-4)
    c["phases"][0]["method"] = "ideal gas"
    r = run_case(c)
    assert r["molar"]["Cp"] == pytest.approx(113.34, rel=REL) and r["molar"]["Cv"] == pytest.approx(105.02, rel=REL)


@pytest.mark.parametrize("P,cp,cv", [(5e5, 45.163, 36.027), (10e5, 46.196, 36.135)])
def test_d8_methane_ethane(P, cp, cv):
    c = get(find("D8"))
    c["P"] = P
    r = run_case(c)
    assert r["molar"]["Cp"] == pytest.approx(cp, rel=REL) and r["molar"]["Cv"] == pytest.approx(cv, rel=REL)


def test_d9_copper():
    """JANAF c_p; c_v from the identity where alpha_V, kappa_T exist (250-350 K), else from Debye."""
    from cpcalc import pure
    c = get(find("D9"))
    c.pop("sweep")
    out = {}
    for T in (100.0, 200.0, 298.15, 400.0, 500.0):
        c["T"] = T
        r = run_case(c)
        out[T] = (r["molar"], r["phases"][0]["method_cv"])
    assert [round(out[T][0]["Cp"], 2) for T in out] == [16.01, 22.63, 24.44, 25.32, 25.91]
    assert [round(out[T][0]["Cv"], 2) for T in (100.0, 200.0, 400.0, 500.0)] == [14.77, 21.63, 24.05, 24.37]
    assert out[298.15][1] == "c_p-c_v identity" and out[298.15][0]["Cp"] - out[298.15][0]["Cv"] == pytest.approx(0.75, abs=0.02)
    assert round(pure.debye_cv(298.15, 343.0, 1), 2) == 23.37          # spec Debye value


def test_d10_d11_errors():
    assert res(find("D10"))["problems"][0]["code"] == "E01"
    assert res(find("D11"))["problems"][0]["code"] == "E04"

"""Workbook, reports, command line, database integrity, engine independence and the web interface."""
import json
import os
import subprocess
import sys

import pytest

from cpcalc import run_case, workbook, report
from cpcalc.database import load_database
from cpcalc.examples import EXAMPLES, get
from cpcalc.errors import CalcError
from cpcalc.latex import to_text
from cpcalc.constants import KINDS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def same(a, b):
    return a["results"] == b["results"] or all(
        (a["results"][k]["value"] or 0) == pytest.approx(b["results"][k]["value"] or 0, rel=1e-12) for k in a["results"])


@pytest.mark.parametrize("name", [n for n in EXAMPLES if not n.startswith("Blank")])
def test_workbook_round_trip(tmp_path, name):
    case = get(name)
    case.pop("sweep", None)
    for path in (str(tmp_path / "c.xlsx"), str(tmp_path / "csvdir")):
        workbook.save_case(case, path, load_database())
        assert same(run_case(case), run_case(workbook.load_case(path)))


def test_bad_workbook_lists_every_cell(tmp_path):
    from openpyxl import load_workbook
    p = str(tmp_path / "bad.xlsx")
    workbook.save_case(get("D3 Al2O3 in water, 2 vol% (spec Fig. 1 values)"), p)
    wb = load_workbook(p)
    wb["Phases"]["B2"] = "plasma"
    wb["Data"]["C2"] = "lots"
    wb["Data"]["B3"] = "colour"
    wb.save(p)
    with pytest.raises(CalcError) as e:
        workbook.load_case(p)
    assert len(e.value.problems) == 3 and all("row" in x["what"] for x in e.value.problems)


def test_reports():
    r = run_case(get("D3 Al2O3 in water, 2 vol% (spec Fig. 1 values)"))
    txt = report.text_report(r, explain=True)
    assert "CALCULATION SHEET" in txt and max(len(l) for l in txt.splitlines()) <= 78
    html = report.html_sheet(r)
    assert "katex" in html and "$$c_v = c_p" in html and "Route taken" in html
    data = json.loads(report.to_json(r))
    for k in ("results", "phases", "steps", "routes", "provenance", "warnings", "assumptions", "timestamp"):
        assert k in data
    assert to_text(r"c_v = c_p - \frac{T\,\alpha_V^{2}}{\rho\,\kappa_T}") == "c_v = c_p - (T alpha_V^2)/(rho kappa_T)"


def test_database_integrity():
    db = load_database()
    assert len(db["components"]) > 150
    for cid, e in db["components"].items():
        for r in e["records"]:
            assert r["kind"] in KINDS and r["source"], (cid, r["key"])
            if "points" in r:
                Ts = [p[0] for p in r["points"]]
                assert all(b > a for a, b in zip(Ts, Ts[1:])), (cid, r["key"])


def test_command_line():
    run = lambda *a: subprocess.run([sys.executable, "-m", "cpcalc", *a], cwd=ROOT, capture_output=True, text=True)
    r = run("example", "D3", "--explain")
    assert r.returncode == 0 and "3925.19" in r.stdout and "Traceback" not in r.stderr
    assert run("example", "D10").returncode == 1
    assert run("example", "nonsense").returncode == 2


def test_engine_needs_no_optional_library():
    code = ("import sys\n"
            "class B:\n"
            "    def find_spec(self, n, p=None, t=None):\n"
            "        if n.split('.')[0] in ('openpyxl','streamlit','pandas','thermo','chemicals','CoolProp','sympy','matplotlib'):\n"
            "            raise ImportError(n)\n"
            "sys.meta_path.insert(0, B())\n"
            "from cpcalc import run_case\nfrom cpcalc.examples import d3\n"
            "print(round(run_case(d3(0.02))['results']['cp_app']['value'], 2))\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "3925.19"


def test_web_interface_runs_every_example():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "cpcalc", "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any(m.value == "3925.19" for m in at.metric)
    assert len(at.tabs) == 5 and len(at.get("latex")) > 10
    for name in at.sidebar.selectbox[0].options:
        at.sidebar.selectbox[0].set_value(name)
        at.sidebar.button[0].click()
        at.run()
        assert not at.exception, name


def test_web_interface_find_and_custom_compound():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "cpcalc", "app.py"), default_timeout=90)
    at.run()
    at.sidebar.text_input[0].input("my nanotubes")
    at.run()
    [b for b in at.sidebar.button if b.label == "Add as my own"][0].click()
    at.run()
    assert not at.exception and any("my nanotubes" in s.value for s in at.sidebar.success)


def test_web_interface_finds_a_compound_in_thermo():
    pytest.importorskip("streamlit")
    pytest.importorskip("thermo")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(ROOT, "cpcalc", "app.py"), default_timeout=120)
    at.run()
    at.sidebar.text_input[0].input("n-butyl acetate")
    at.run()
    [b for b in at.sidebar.button if b.label == "Find in thermo"][0].click()
    at.run()
    assert not at.exception and any("Added" in s.value for s in at.sidebar.success)

"""Command line (all printing lives here).

  python -m cpcalc ui                      open the web interface (Streamlit)
  python -m cpcalc examples                list the ready-made cases
  python -m cpcalc example D3 [--explain]  run one example ('all' runs every one)
  python -m cpcalc run case.xlsx [--explain] [--html sheet.html]
  python -m cpcalc template --out case.xlsx [--example D3]
  python -m cpcalc test                    run the test suites
"""
import argparse
import os
import subprocess
import sys

from . import examples, report, workbook, database
from .engine import run_case, run_sweep
from .errors import CalcError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_example(key):
    for name in examples.EXAMPLES:
        if name.lower().startswith(key.lower()):
            return name
    return None


def show_case(case, explain=False, html=None):
    try:
        res = run_case(case)
    except CalcError as err:
        print(report.problems_text(err.problems))
        return 2
    print(report.text_report(res, explain))
    if case.get("sweep"):
        print()
        print(report.sweep_text(run_sweep(case)))
    if html:
        with open(html, "w", encoding="utf-8") as fh:
            fh.write(report.html_sheet(res))
        print("calculation sheet written to", html)
    return 0 if res["status"] != "not calculable" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m cpcalc")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("ui")
    sub.add_parser("examples")
    p = sub.add_parser("example")
    p.add_argument("name")
    p.add_argument("--explain", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("path")
    p.add_argument("--explain", action="store_true")
    p.add_argument("--html")
    p = sub.add_parser("template")
    p.add_argument("--out", default="cpcalc_case.xlsx")
    p.add_argument("--example", default="Blank")
    sub.add_parser("test")
    a = ap.parse_args(argv)
    if a.cmd in (None, "ui"):
        app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        return subprocess.call([sys.executable, "-m", "streamlit", "run", app])
    if a.cmd == "examples":
        for name in examples.EXAMPLES:
            print(" ", name)
        return 0
    if a.cmd == "example":
        names = list(examples.EXAMPLES) if a.name.lower() == "all" else [find_example(a.name)]
        if None in names:
            print("unknown example '%s'; see: python -m cpcalc examples" % a.name)
            return 2
        code = 0
        for name in names:
            print("=" * 78)
            print(name)
            print("=" * 78)
            code = max(code, show_case(examples.get(name), a.explain) if name != "Blank" else 0)
        return 0 if a.name.lower() == "all" else code
    if a.cmd == "run":
        try:
            case = workbook.load_case(a.path)
        except CalcError as err:
            print(report.problems_text(err.problems))
            return 2
        return show_case(case, a.explain, a.html)
    if a.cmd == "template":
        name = find_example(a.example) or "Blank"
        workbook.save_case(examples.get(name), a.out, database.load_database())
        print("written", os.path.abspath(a.out))
        return 0
    if a.cmd == "test":
        return subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", "validate"], cwd=ROOT)
    return 0

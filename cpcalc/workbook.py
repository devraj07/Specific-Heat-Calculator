"""Excel workbook (or a folder of CSV files) <-> case dictionary.
Six sheets: Setup, Phases, Mixtures, Data, Curves, Pairs (+ a read-only Compounds list)."""
import csv
import os

from .constants import STATES, ROLES, PURE_METHODS, MIX_MODELS, MIX_BASES, KINDS, PROPS, PAIR_KEYS
from .errors import CalcError, problem
from .units import temperature_K, pressure_Pa

SHEETS = {
    "Setup": ["key", "value", "unit"],
    "Phases": ["name", "state", "substance", "amount", "role", "method"],
    "Mixtures": ["mixture", "component", "fraction", "basis", "model"],
    "Data": ["component", "property", "value", "unit", "state", "T_min", "T_max", "kind", "source"],
    "Curves": ["component", "property", "state", "T", "value", "unit", "kind", "source"],
    "Pairs": ["component_i", "component_j", "parameter", "value", "kind", "source"],
}
SETUP_KEYS = ["name", "T", "P", "quantity", "basis", "sweep_variable", "sweep_start", "sweep_stop", "sweep_n", "sweep_target"]


# ------------------------------------------------------------------ reading
def _rows_xlsx(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    return {ws.title.strip().lower(): list(ws.iter_rows(values_only=True)) for ws in wb.worksheets}


def _rows_csv(folder):
    out = {}
    for fn in os.listdir(folder):
        if fn.lower().endswith(".csv"):
            with open(os.path.join(folder, fn), newline="", encoding="utf-8-sig") as fh:
                out[fn[:-4].strip().lower()] = [tuple(r) for r in csv.reader(fh)]
    return out


def _table(raw, sheet):
    rows = raw.get(sheet.lower(), [])
    if not rows:
        return []
    head = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for n, r in enumerate(rows[1:], start=2):
        rec = {"_row": n}
        for h, v in zip(head, r):
            if isinstance(v, str):
                v = v.strip() or None
            rec[h] = v
        if any(rec.get(h) is not None for h in head if h):
            out.append(rec)
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_case(path):
    """Read a workbook or CSV folder into a case dict; raises CalcError listing every bad cell."""
    raw = _rows_csv(path) if os.path.isdir(path) else _rows_xlsx(path)
    errs = []

    def bad(sheet, rec, col, text):
        errs.append(problem("E02", "%s row %s, column '%s': %s" % (sheet, rec["_row"], col, text)))

    for s in ("setup", "phases"):
        if s not in raw:
            errs.append(problem("E02", "sheet '%s' is missing" % s.capitalize()))
    case = {"phases": [], "mixtures": {}, "data": [], "curves": [], "pairs": []}
    sweep = {}
    for rec in _table(raw, "Setup"):
        key, value, unit = rec.get("key"), rec.get("value"), rec.get("unit")
        if key not in SETUP_KEYS:
            bad("Setup", rec, "key", "unknown setting '%s' (use %s)" % (key, ", ".join(SETUP_KEYS)))
            continue
        try:
            if key == "T":
                case["T"] = temperature_K(value, unit or "K")
            elif key == "P":
                case["P"] = pressure_Pa(value, unit or "Pa")
            elif key.startswith("sweep_"):
                k = key[6:]
                sweep[k] = _num(value) if k in ("start", "stop", "n") else value
                if k in ("start", "stop") and unit in ("C",) and sweep.get("variable", "T") == "T":
                    sweep[k] = temperature_K(value, "C")
            else:
                case[key] = value
        except CalcError as e:
            bad("Setup", rec, "unit", e.problems[0]["what"])
    if sweep.get("variable") and str(sweep["variable"]).lower() not in ("", "none"):
        case["sweep"] = {"variable": sweep["variable"], "start": sweep.get("start"), "stop": sweep.get("stop"),
                         "n": int(sweep.get("n") or 11), "target": sweep.get("target") or ""}
    for rec in _table(raw, "Phases"):
        state = str(rec.get("state") or "").lower()
        if state not in STATES:
            bad("Phases", rec, "state", "must be one of %s" % ", ".join(STATES))
        if _num(rec.get("amount")) is None:
            bad("Phases", rec, "amount", "not a number")
        case["phases"].append({"name": rec.get("name"), "state": state, "substance": rec.get("substance"),
                               "amount": _num(rec.get("amount")), "role": rec.get("role") or "",
                               "method": rec.get("method") or "auto"})
    for rec in _table(raw, "Mixtures"):
        name = rec.get("mixture")
        m = case["mixtures"].setdefault(name, {"basis": rec.get("basis") or "mole", "model": rec.get("model") or "auto",
                                               "components": {}})
        if _num(rec.get("fraction")) is None:
            bad("Mixtures", rec, "fraction", "not a number")
        m["components"][rec.get("component")] = _num(rec.get("fraction"))
    for rec in _table(raw, "Data"):
        if rec.get("property") not in PROPS:
            bad("Data", rec, "property", "unknown property (use %s)" % ", ".join(PROPS))
        if _num(rec.get("value")) is None:
            bad("Data", rec, "value", "not a number")
        if rec.get("kind") and rec["kind"] not in KINDS:
            bad("Data", rec, "kind", "use one of %s" % ", ".join(KINDS))
        case["data"].append({"component": rec.get("component"), "key": rec.get("property"), "value": _num(rec.get("value")),
                             "unit": rec.get("unit"), "state": rec.get("state") or "", "T_min": _num(rec.get("T_min")),
                             "T_max": _num(rec.get("T_max")), "kind": rec.get("kind") or "unspecified",
                             "source": rec.get("source") or ""})
    curves = {}
    for rec in _table(raw, "Curves"):
        key = (rec.get("component"), rec.get("property"), rec.get("state") or "")
        if _num(rec.get("T")) is None or _num(rec.get("value")) is None:
            bad("Curves", rec, "T/value", "not a number")
            continue
        cu = curves.setdefault(key, {"component": key[0], "key": key[1], "state": key[2], "unit": rec.get("unit"),
                                     "kind": rec.get("kind") or "unspecified", "source": rec.get("source") or "", "points": []})
        cu["points"].append([_num(rec["T"]), _num(rec["value"])])
    case["curves"] = list(curves.values())
    for rec in _table(raw, "Pairs"):
        if rec.get("parameter") not in PAIR_KEYS:
            bad("Pairs", rec, "parameter", "use one of %s" % ", ".join(PAIR_KEYS))
        case["pairs"].append({"i": rec.get("component_i"), "j": rec.get("component_j"), "key": rec.get("parameter"),
                              "value": _num(rec.get("value")), "kind": rec.get("kind") or "unspecified",
                              "source": rec.get("source") or ""})
    if errs:
        raise CalcError(errs)
    return case


# ------------------------------------------------------------------ writing
def case_rows(case):
    rows = {s: [] for s in SHEETS}
    for k in ("name", "T", "P", "quantity", "basis"):
        if k in case:
            rows["Setup"].append({"key": k, "value": case[k], "unit": {"T": "K", "P": "Pa"}.get(k)})
    if case.get("sweep"):
        for k, v in case["sweep"].items():
            rows["Setup"].append({"key": "sweep_" + k, "value": v, "unit": "K" if (k in ("start", "stop") and case["sweep"]["variable"] == "T") else None})
    rows["Phases"] = [dict(p) for p in case.get("phases", [])]
    for name, m in (case.get("mixtures") or {}).items():
        for c, x in m["components"].items():
            rows["Mixtures"].append({"mixture": name, "component": c, "fraction": x, "basis": m.get("basis"), "model": m.get("model")})
    for d in case.get("data", []):
        rows["Data"].append(dict(d, property=d["key"]))
    for cu in case.get("curves", []):
        for T, v in cu["points"]:
            rows["Curves"].append({"component": cu["component"], "property": cu["key"], "state": cu.get("state"), "T": T,
                                   "value": v, "unit": cu.get("unit"), "kind": cu.get("kind"), "source": cu.get("source")})
    for p in case.get("pairs", []):
        rows["Pairs"].append({"component_i": p["i"], "component_j": p["j"], "parameter": p["key"], "value": p["value"],
                              "kind": p.get("kind"), "source": p.get("source")})
    return rows


def save_case(case, path, db=None):
    """Write .xlsx (with drop-down lists) or, for a path without .xlsx, a folder of CSV files."""
    rows = case_rows(case)
    if not path.lower().endswith(".xlsx"):
        os.makedirs(path, exist_ok=True)
        for s, cols in SHEETS.items():
            with open(os.path.join(path, s + ".csv"), "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for r in rows[s]:
                    w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
        return path
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    wb.remove(wb.active)
    head = PatternFill("solid", fgColor="DDE7F0")
    for s, cols in SHEETS.items():
        ws = wb.create_sheet(s)
        ws.append(cols)
        for cell in ws[1]:
            cell.font, cell.fill = Font(bold=True), head
        for r in rows[s]:
            ws.append([r.get(c) for c in cols])
        for i, c in enumerate(cols):
            ws.column_dimensions[chr(65 + i)].width = max(12, len(c) + 4) if c != "source" else 50
    lists = {("Phases", "state"): STATES, ("Phases", "role"): ROLES,
             ("Phases", "method"): ["auto"] + sorted({m for v in PURE_METHODS.values() for m in v}),
             ("Mixtures", "basis"): MIX_BASES, ("Mixtures", "model"): MIX_MODELS, ("Data", "kind"): KINDS,
             ("Data", "property"): list(PROPS), ("Data", "state"): STATES, ("Curves", "kind"): KINDS,
             ("Curves", "property"): list(PROPS), ("Curves", "state"): STATES, ("Pairs", "parameter"): PAIR_KEYS,
             ("Pairs", "kind"): KINDS}
    for (s, col), opts in lists.items():
        letter = chr(65 + SHEETS[s].index(col))
        dv = DataValidation(type="list", formula1='"%s"' % ",".join(opts), allow_blank=True)
        wb[s].add_data_validation(dv)
        dv.add("%s2:%s400" % (letter, letter))
    if db is not None:
        ws = wb.create_sheet("Compounds")
        ws.append(["id (type this or pick from the list)", "name", "CAS", "data from"])
        for cid in sorted(db["components"]):
            e = db["components"][cid]
            ws.append([cid, e.get("name"), e.get("cas"), e.get("origin")])
        n = len(db["components"]) + 1
        for s, col in (("Phases", "substance"), ("Mixtures", "component"), ("Data", "component"), ("Curves", "component")):
            letter = chr(65 + SHEETS[s].index(col))
            dv = DataValidation(type="list", formula1="Compounds!$A$2:$A$%d" % n, allow_blank=True, showErrorMessage=False)
            wb[s].add_data_validation(dv)
            dv.add("%s2:%s400" % (letter, letter))
    wb.save(path)
    return path

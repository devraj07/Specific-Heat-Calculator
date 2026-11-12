"""Find one property of one compound at the run temperature.

Order (first success wins):
  1. your single value valid at T     2. your curve containing T
  3. database value                   4. database curve containing T
  5. derived: alpha_V = -(1/rho) d rho/dT from a rho curve
Nothing is ever extrapolated. If nothing is found, the reasons are kept in
ctx["tried"] so that the engine can explain what is missing.
"""
from . import database
from .constants import KINDS, CONSTANT_KEYS, PROPS
from .errors import CalcError
from .units import to_si, needs_M

T_TOL = 0.05      # K: a run temperature this close to a curve end uses the end value


def canon(db, name):
    """Canonical id of a compound: its database id if known, else the lower-case name."""
    cid = database.find(db, name)
    return cid if cid else str(name).strip().lower()


def new_context(case, db):
    return {"case": case, "db": db, "T": case["T"], "P": case["P"], "cache": {}, "tried": {},
            "out_of_range": {}, "used": [], "warnings": [], "notes": [], "assumptions": [],
            "steps": [], "routes": {}, "illustrative": []}


def weakest(kinds):
    worst = "experimental"
    for k in kinds:
        k = k if k in KINDS else "unspecified"
        if KINDS.index(k) > KINDS.index(worst):
            worst = k
    return worst


def warn(ctx, code, text):
    if not any(w["code"] == code and w["text"] == text for w in ctx["warnings"]):
        ctx["warnings"].append({"code": code, "text": text})


def note(ctx, text):
    if text not in ctx["notes"]:
        ctx["notes"].append(text)


def assume(ctx, name, detail=""):
    if not any(a["name"] == name and a["detail"] == detail for a in ctx["assumptions"]):
        ctx["assumptions"].append({"name": name, "detail": detail})


def use(ctx, rec):
    """Put a record (and what it was built from) in the provenance table."""
    if rec is None:
        return
    for r in rec.get("inputs", []):
        use(ctx, r)
    if any(u["comp"] == rec["comp"] and u["key"] == rec["key"] and u["route"] == rec["route"] for u in ctx["used"]):
        return
    ctx["used"].append(rec)
    if rec["kind"] == "illustrative":
        ctx["illustrative"].append("%s of %s" % (rec["key"], rec["comp"]))
    if rec.get("no_range"):
        assume(ctx, "no_T_range", "%s of %s" % (rec["key"], rec["comp"]))
    if rec.get("db_diff") is not None:
        warn(ctx, "A09", "your %s of %s differs from the database by %+.1f %%" % (rec["key"], rec["comp"], rec["db_diff"]))


# ------------------------------------------------------------------ evaluation of one stored item
def _state_ok(item, key, state):
    tag = (item.get("state") or "").lower()
    return not tag or not state or key in CONSTANT_KEYS or key == "cp_ig" or tag == state


def interpolate(points, T):
    """Linear interpolation; None outside the table (never extrapolated)."""
    if T < points[0][0] - T_TOL or T > points[-1][0] + T_TOL:
        return None
    T = min(max(T, points[0][0]), points[-1][0])
    for (T0, y0), (T1, y1) in zip(points, points[1:]):
        if T <= T1:
            return y0 + (y1 - y0) * (T - T0) / (T1 - T0)
    return points[-1][1]


def slope(points, T):
    """d y/dT of a curve at T (slope of the segment, or mean of two neighbouring segments at a node)."""
    T = min(max(T, points[0][0]), points[-1][0])
    for i, ((T0, y0), (T1, y1)) in enumerate(zip(points, points[1:])):
        if T0 <= T <= T1:
            s = (y1 - y0) / (T1 - T0)
            if T == T1 and i + 2 < len(points):
                s = 0.5 * (s + (points[i + 2][1] - y1) / (points[i + 2][0] - T1))
            return s
    return None


def _range(item):
    if "points" in item:
        return (item["points"][0][0], item["points"][-1][0])
    return (item.get("T_min"), item.get("T_max"))


def _value_at(item, key, T):
    """(value, ok). Single values with a T range are valid only inside it."""
    if "points" in item:
        y = interpolate(item["points"], T)
        return y, y is not None
    lo, hi = item.get("T_min"), item.get("T_max")
    if key in CONSTANT_KEYS or (lo is None and hi is None):
        return item["value"], True
    ok = (lo is None or T >= lo - T_TOL) and (hi is None or T <= hi + T_TOL)
    return item["value"], ok


def range_text(rng):
    lo, hi = rng
    if lo is None and hi is None:
        return "any T"
    if lo == hi:
        return "%.2f K only" % lo
    return "%s-%s K" % ("%.2f" % lo if lo is not None else "...", "%.2f" % hi if hi is not None else "...")


# ------------------------------------------------------------------ main lookup
def find(ctx, comp, key, state=""):
    """Record {comp, key, value (SI), unit, kind, source, route, ...} or None."""
    ck = (comp, key, state)
    if ck in ctx["cache"]:
        return ctx["cache"][ck]
    ctx["cache"][ck] = None
    T, case, db = ctx["T"], ctx["case"], ctx["db"]
    tried, ranges = [], []
    candidates = [("yours", i) for i in case["data"] if i["component"] == comp and i["key"] == key]
    candidates += [("your curve", i) for i in case["curves"] if i["component"] == comp and i["key"] == key]
    db_items = database.records(db, comp, key)
    candidates += [("database", i) for i in db_items if "points" not in i]
    candidates += [("database curve", i) for i in db_items if "points" in i]
    rec = None
    for route, item in candidates:
        if not _state_ok(item, key, state):
            tried.append("%s: given for %s, not %s" % (route, item.get("state"), state))
            continue
        value, ok = _value_at(item, key, T)
        if not ok:
            ranges.append(_range(item))
            tried.append("%s: valid %s" % (route, range_text(_range(item))))
            continue
        rec, why = _record(ctx, comp, key, route, item, value)
        if rec:
            break
        tried.append(why)
    if rec is None and key == "alpha_V":
        rec = _alpha_from_rho(ctx, comp, state, tried)
    if rec is not None and rec["route"] in ("yours", "your curve"):
        _compare(ctx, comp, key, state, rec)
    if rec is None and not tried:
        tried.append("not given and not in the database")
    ctx["tried"][ck] = tried
    ctx["out_of_range"][ck] = ranges
    ctx["cache"][ck] = rec
    return rec


def _record(ctx, comp, key, route, item, value):
    inputs, M = [], None
    if needs_M(key, item.get("unit")):
        m = find(ctx, comp, "M", "")
        if m is None:
            return None, "%s: given per %s, so the molar mass M is needed (missing)" % (
                route, "mole" if "mol" in item.get("unit", "") else "kg")
        M, inputs = m["value"], [m]
    si = to_si(key, value, item.get("unit"), M)
    no_range = (route == "yours" and key not in CONSTANT_KEYS and item.get("T_min") is None
                and item.get("T_max") is None)
    return {"comp": comp, "key": key, "value": si, "unit": PROPS[key][2],
            "given": "%.6g %s" % (value, item.get("unit", "")), "kind": weakest([item.get("kind", "unspecified")] +
                                                                              [i["kind"] for i in inputs]),
            "source": item.get("source") or "(no source given)", "route": route, "range": _range(item),
            "note": item.get("note", ""), "inputs": inputs, "no_range": no_range}, ""


def _alpha_from_rho(ctx, comp, state, tried):
    curves = [("your curve", i) for i in ctx["case"]["curves"] if i["component"] == comp and i["key"] == "rho"]
    curves += [("database curve", i) for i in database.records(ctx["db"], comp, "rho") if "points" in i]
    for route, item in curves:
        if not _state_ok(item, "rho", state):
            continue
        rho = interpolate(item["points"], ctx["T"])
        if rho is None:
            continue
        a = -slope(item["points"], ctx["T"]) / rho
        return {"comp": comp, "key": "alpha_V", "value": a, "unit": "1/K", "given": "from the rho curve",
                "kind": weakest(["derived", item.get("kind", "unspecified")]),
                "source": "derived: alpha_V = -(1/rho) d rho/dT of %s (%s)" % (route, item.get("source", "")),
                "route": "derived", "range": _range(item), "note": "", "inputs": [], "no_range": False}
    tried.append("derived: needs rho at two or more temperatures (a rho curve)")
    return None


def _compare(ctx, comp, key, state, rec):
    for item in database.records(ctx["db"], comp, key):
        if not _state_ok(item, key, state):
            continue
        value, ok = _value_at(item, key, ctx["T"])
        if not ok:
            continue
        try:
            M = None
            if needs_M(key, item.get("unit")):
                m = find(ctx, comp, "M", "")
                M = m["value"] if m else None
            dbv = to_si(key, value, item.get("unit"), M)
        except CalcError:
            return
        if dbv and abs(rec["value"] / dbv - 1) > 0.05:
            rec["db_diff"] = 100 * (rec["value"] / dbv - 1)
        return


def preview(case, db, comp, key, state):
    """For the UI data-check table: what would be used at the case temperature."""
    ctx = new_context(case, db)
    rec = find(ctx, comp, key, state)
    tried = ctx["tried"].get((comp, key, state), [])
    return rec, tried

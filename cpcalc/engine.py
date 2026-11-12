"""The calculation engine.

    result = run_case(case)        one temperature
    results = run_sweep(case)      a range of T, phase fraction or composition

A case is a plain dictionary (see examples.py); the result is a plain dictionary.
The engine never prints and never reads files other than the database.

Flow for every phase: try its methods in order (or the one you chose), record what
each method was missing, then assemble the sample with Eq. 20 (c_p) and Eq. 21 (c_v).
Every equation used is written to result["steps"] in LaTeX (the calculation sheet).
"""
import copy

from . import database, pure, sample
from . import mixtures as mx
from .constants import (R, KINDS, PROPS, STATES, ROLES, PURE_METHODS, AUTO_PURE, MIX_MODELS, MIX_BASES,
                        PAIR_KEYS, ASSUMPTIONS, STANDING_ASSUMPTIONS, WHERE_TO_LOOK, DEFAULTS, P_ATM)
from .errors import CalcError, problem
from .latex import num, q
from .properties import canon, new_context, find, use, warn, note, assume, weakest, range_text
from .units import to_si, clean_unit, allowed_units

VERSION = "3.0"
ROUTE_NAMES = {"yours": "your value", "your curve": "your curve (interpolated)", "database": "database value",
               "database curve": "database curve (interpolated)", "derived": "derived"}


# ================================================================== small helpers
def step(ctx, title, eq="", sub="", res="", ref="", info="", phase=""):
    """One line of the calculation sheet (LaTeX strings)."""
    ctx["steps"].append({"title": title, "eq": eq, "sub": sub, "res": res, "ref": ref, "info": info, "phase": phase})


def new_need():
    return {"recs": [], "missing": []}


def get(ctx, need, comp, key, state=""):
    rec = find(ctx, comp, key, state)
    if rec is None:
        need["missing"].append((comp, key, state))
        return None
    need["recs"].append(rec)
    return rec["value"]


def optional(ctx, need, comp, key, state=""):
    rec = find(ctx, comp, key, state)
    if rec is not None:
        need["recs"].append(rec)
        return rec["value"]
    return None


def accept(ctx, need):
    for r in need["recs"]:
        use(ctx, r)


def blank_bundle(ph):
    return {"name": ph["name"], "state": ph["state"], "substance": ph["substance"], "role": ph["role"],
            "amount": ph["amount"], "cp": None, "cv": None, "rho": None, "alpha": None, "kappa": None, "M": None,
            "Cp_molar": None, "Cv_molar": None, "method_cp": "", "method_cv": "", "label": "", "extra": {}}


def record_route(ctx, ph, quantity, tries, chosen, how):
    tried = []
    for method, need in tries:
        tried.append({"method": method, "lacks": [_missing_text(ph, m) for m in need["missing"]]})
    ctx["routes"].setdefault(ph["name"], []).append({"quantity": quantity, "tried": tried, "chosen": chosen, "how": how})


def _missing_text(ph, m):
    if isinstance(m, str):
        return m
    if m[0] == "error":
        return m[2]
    comp, key, state = m
    return key if comp == ph["substance"] else "%s of %s" % (key, comp)


# ================================================================== 1. check the input
def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def check_case(case, db):
    """Clean copy of the case with defaults filled in; raises CalcError listing all input problems."""
    probs, warns = [], []
    c = copy.deepcopy(case)
    for k, v in DEFAULTS.items():
        if k not in c or c[k] == "" or (c[k] is None and k != "phi_warn"):
            c[k] = v
    for k in ("T", "P"):
        if _num(c[k]) is None or _num(c[k]) <= 0:
            probs.append(problem("E07", "%s = %r must be a positive number (K, Pa)" % (k, c[k])))
        else:
            c[k] = float(c[k])
    c["quantity"] = str(c["quantity"]).lower()
    c["basis"] = str(c["basis"]).lower()
    if c["quantity"] not in ("cp", "cv", "both"):
        probs.append(problem("E09", "quantity must be cp, cv or both"))
    if c["basis"] not in ("mass", "volume"):
        probs.append(problem("E03", "phase amounts must be given as mass or volume fractions"))
    for term in c.get("optional_terms") or []:
        probs.append(problem("E09", "the %s term is not part of this model" % term,
                             "the model is frozen-phase with the interface neglected (spec R6, Sec. 3.7)"))
    # mixtures
    mixes = {}
    for name, m in (c.get("mixtures") or {}).items():
        key = str(name).strip().lower()
        basis = str(m.get("basis", "mole")).lower()
        model = m.get("model") or "auto"
        if basis not in MIX_BASES:
            probs.append(problem("E03", "mixture '%s': basis must be mole, mass or volume" % name))
        if model not in MIX_MODELS:
            probs.append(problem("E09", "mixture '%s': model '%s' unknown (%s)" % (name, model, ", ".join(MIX_MODELS))))
        comps = {}
        for comp, f in (m.get("components") or {}).items():
            x = _num(f)
            if x is None or x < 0:
                probs.append(problem("E03", "mixture '%s': fraction of %s must be a number >= 0" % (name, comp)))
                continue
            cid = canon(db, comp)
            comps[cid] = comps.get(cid, 0.0) + x
        total = sum(comps.values())
        if len(comps) < 1 or abs(total - 1) > 1e-3:
            probs.append(problem("E03", "mixture '%s': fractions sum to %.5f, not 1" % (name, total),
                                 "correct the fractions (a difference up to 0.001 is renormalised)"))
        elif abs(total - 1) > 1e-12:
            warns.append(("A02", "mixture '%s': fractions summed to %.6f and were renormalised" % (name, total)))
            comps = {k: v / total for k, v in comps.items()}
        mixes[key] = {"name": name, "basis": basis, "model": model, "components": comps}
    c["mixtures"] = mixes
    # phases
    phases, seen = [], set()
    for i, ph in enumerate(c.get("phases") or []):
        name = str(ph.get("name") or "phase %d" % (i + 1)).strip()
        if name.lower() in seen:
            probs.append(problem("E10", "two phases are called '%s'" % name))
        seen.add(name.lower())
        state = str(ph.get("state", "")).lower()
        if state not in STATES:
            probs.append(problem("E02", "phase '%s': state must be liquid, solid or gas" % name))
            continue
        sub = str(ph.get("substance") or "").strip()
        if not sub:
            probs.append(problem("E10", "phase '%s' has no substance" % name))
            continue
        is_mix = sub.lower() in mixes
        method = ph.get("method") or "auto"
        if not is_mix and method != "auto" and method not in PURE_METHODS[state]:
            probs.append(problem("E09", "phase '%s': method '%s' is not available for a %s (%s)" % (
                name, method, state, ", ".join(["auto"] + PURE_METHODS[state]))))
        amount = _num(ph.get("amount"))
        if amount is None or amount < 0:
            probs.append(problem("E03", "phase '%s': amount must be a number >= 0" % name))
            continue
        role = str(ph.get("role") or ("continuous" if i == 0 else "dispersed")).lower()
        phases.append({"name": name, "state": state, "substance": sub.lower() if is_mix else canon(db, sub),
                       "is_mixture": is_mix, "amount": amount, "role": role if role in ROLES else "dispersed",
                       "method": method})
    if not phases and not probs:
        probs.append(problem("E02", "the case has no phases"))
    total = sum(p["amount"] for p in phases)
    if phases and abs(total - 1) > 1e-3:
        probs.append(problem("E03", "phase %s fractions sum to %.5f, not 1" % (c["basis"], total),
                             "correct the amounts (a difference up to 0.001 is renormalised)"))
    elif phases and abs(total - 1) > 1e-12:
        warns.append(("A02", "phase fractions summed to %.6f and were renormalised" % total))
        for p in phases:
            p["amount"] /= total
    c["phases"] = phases
    # data, curves, pairs
    data = []
    for i, r in enumerate(c.get("data") or []):
        r = dict(r)
        where = "data row %d (%s, %s)" % (i + 1, r.get("component"), r.get("key"))
        if r.get("key") not in PROPS:
            probs.append(problem("E02", "%s: unknown property" % where, "use one of " + ", ".join(PROPS)))
            continue
        if _num(r.get("value")) is None:
            probs.append(problem("E02", "%s: value %r is not a number" % (where, r.get("value"))))
            continue
        if clean_unit(r.get("unit") or PROPS[r["key"]][2]) not in [clean_unit(u) for u in allowed_units(r["key"])] + ["-", ""]:
            probs.append(problem("E02", "%s: unit '%s' does not fit %s" % (where, r.get("unit"), r["key"]),
                                 "allowed: " + ", ".join(allowed_units(r["key"]))))
            continue
        r["value"] = float(r["value"])
        r["unit"] = r.get("unit") or PROPS[r["key"]][2]
        if r["key"] in ("cp", "cp_ig", "rho", "kappa_T", "M", "Tc", "Pc", "theta_D", "n_atoms") and r["value"] <= 0:
            probs.append(problem("E07", "%s: %s must be > 0" % (where, r["key"])))
        for b in ("T_min", "T_max"):
            r[b] = _num(r.get(b))
        if r["T_min"] is not None and r["T_max"] is not None and r["T_min"] > r["T_max"]:
            probs.append(problem("E02", "%s: T_min > T_max" % where))
        r["component"] = canon(db, r.get("component", ""))
        r["state"] = (r.get("state") or "").lower()
        r["kind"] = r.get("kind") if r.get("kind") in KINDS else "unspecified"
        data.append(r)
    c["data"] = data
    curves = []
    for cu in c.get("curves") or []:
        cu = dict(cu)
        pts = sorted([[float(t), float(v)] for t, v in cu.get("points", []) if _num(t) is not None and _num(v) is not None])
        where = "curve %s of %s" % (cu.get("key"), cu.get("component"))
        if cu.get("key") not in PROPS:
            probs.append(problem("E02", "%s: unknown property" % where))
            continue
        if len(pts) < 2 or any(b[0] <= a[0] for a, b in zip(pts, pts[1:])):
            probs.append(problem("E02", "%s needs at least 2 points with different temperatures" % where))
            continue
        cu.update({"points": pts, "component": canon(db, cu.get("component", "")), "state": (cu.get("state") or "").lower(),
                   "unit": cu.get("unit") or PROPS[cu["key"]][2],
                   "kind": cu.get("kind") if cu.get("kind") in KINDS else "unspecified"})
        curves.append(cu)
    c["curves"] = curves
    pairs = []
    for p in c.get("pairs") or []:
        if p.get("key") not in PAIR_KEYS or _num(p.get("value")) is None:
            probs.append(problem("E02", "pair parameter %r is not valid (keys: %s)" % (p.get("key"), ", ".join(PAIR_KEYS))))
            continue
        pairs.append(dict(p, i=canon(db, p.get("i", "")), j=canon(db, p.get("j", "")), value=float(p["value"]),
                          kind=p.get("kind") if p.get("kind") in KINDS else "unspecified"))
    c["pairs"] = pairs
    if probs:
        raise CalcError(probs)
    c["_warnings"] = warns
    return c


# ================================================================== 2. methods for a pure phase
def m_data(ctx, ph, need, with_cp=True):
    cp = get(ctx, need, ph["substance"], "cp", ph["state"])
    if cp is None:
        return None
    rec = need["recs"][-1]
    step(ctx, "c_p of '%s' from data" % ph["name"], r"c_p = c_p(T)", "",
         r"c_p = %s" % q(cp, "J/kg/K"), "", "%s: %s" % (ROUTE_NAMES.get(rec["route"], rec["route"]), rec["source"]), ph["name"])
    return {"cp": cp}


def cv_identity(ctx, ph, bundle, need):
    comp, state = ph["substance"], ph["state"]
    if bundle["cp"] is None:
        need["missing"].append("c_p of the phase")
    rho = bundle["rho"] if bundle["rho"] is not None else get(ctx, need, comp, "rho", state)
    alpha = bundle["alpha"] if bundle["alpha"] is not None else get(ctx, need, comp, "alpha_V", state)
    kappa = bundle["kappa"] if bundle["kappa"] is not None else get(ctx, need, comp, "kappa_T", state)
    if need["missing"]:
        return None
    T = ctx["T"]
    d = pure.cp_minus_cv(T, rho, alpha, kappa)
    cv = bundle["cp"] - d
    step(ctx, "c_v of '%s' from the c_p - c_v identity" % ph["name"],
         r"c_v = c_p - \frac{T\,\alpha_V^{2}}{\rho\,\kappa_T}",
         r"c_v = %s - \frac{%s\times(%s)^{2}}{%s\times %s} = %s - %s" % (
             num(bundle["cp"]), num(T), num(alpha), num(rho), num(kappa), num(bundle["cp"]), num(d)),
         r"c_v = %s" % q(cv, "J/kg/K"), "Eq. (3), (12)", "", ph["name"])
    return {"cv": cv, "rho": rho, "alpha": alpha, "kappa": kappa}


def m_ideal_gas(ctx, ph, need, with_cp=True):
    comp = ph["substance"]
    cp_ig = get(ctx, need, comp, "cp_ig", "gas")
    M = get(ctx, need, comp, "M")
    if need["missing"]:
        return None
    T, P = ctx["T"], ctx["P"]
    step(ctx, "'%s' as an ideal gas" % ph["name"], r"C_p = C_p^{ig}(T), \qquad C_v = C_p^{ig} - R",
         r"C_v = %s - %s" % (num(cp_ig), num(R)),
         r"C_p = %s,\quad C_v = %s" % (q(cp_ig, "J/mol/K"), q(cp_ig - R, "J/mol/K")), "Eq. (5), zero departure",
         "compressibility is not checked on this route", ph["name"])
    return {"cp": cp_ig / M, "cv": (cp_ig - R) / M, "Cp_molar": cp_ig, "Cv_molar": cp_ig - R, "M": M,
            "rho": P * M / (R * T), "alpha": 1.0 / T, "kappa": 1.0 / P, "label": "ideal gas"}


def _pr_flags(ctx, ph, comp, T, Tc, omega, liquid):
    if 0.95 < T / Tc < 1.05:
        warn(ctx, "A04", "%s is near its critical point (T/Tc = %.3f)" % (comp, T / Tc))
    e = database.entry(ctx["db"], comp)
    if e and e.get("associating"):
        warn(ctx, "A06", "Peng-Robinson used for %s, which associates (hydrogen bonds)" % comp)
    if liquid:
        warn(ctx, "A11", "Peng-Robinson liquid for '%s': caloric errors up to ~26 %% (spec Table 3)" % ph["name"])
    if omega > 0.491:
        warn(ctx, "A12", "PR78 m(omega) used for %s (omega = %.3f)" % (comp, omega))


def _pr_steps(ctx, ph, label, p, st, cp_ig):
    step(ctx, "Peng-Robinson parameters (%s)" % label,
         r"a = 0.45724\frac{R^2T_c^2}{P_c}\left[1+m\left(1-\sqrt{T/T_c}\right)\right]^2,\quad b = 0.07780\frac{RT_c}{P_c}",
         r"a = %s,\; a' = %s,\; a'' = %s,\; b = %s" % (num(p["a"]), num(p["da"]), num(p["d2a"]), num(p["b"])),
         "", "Eq. (6)-(8)", "", ph["name"])
    step(ctx, "Cubic in Z and choice of root",
         r"Z^3-(1-B)Z^2+(A-3B^2-2B)Z-(AB-B^2-B^3)=0",
         r"A = %s,\; B = %s,\; \text{real roots: } %s" % (num(st["A"]), num(st["B"]), ",\\ ".join(num(z) for z in st["roots"])),
         r"Z = %s\ (\text{%s})" % (num(st["Z"]), st["label"]), "Eq. (10), rules P1-P4", "", ph["name"])
    step(ctx, "Residual heat capacity",
         r"C_v^R = \frac{T\,a''}{2\sqrt{2}\,b}\ln\frac{v+(1+\sqrt{2})b}{v+(1-\sqrt{2})b},\qquad "
         r"C_p - C_v = -T\frac{(\partial P/\partial T)_v^2}{(\partial P/\partial v)_T}",
         r"v = %s,\; (\partial P/\partial T)_v = %s,\; (\partial P/\partial v)_T = %s" % (
             q(st["v"], "m3/mol"), num(st["dPdT"]), num(st["dPdv"])),
         r"C_v^R = %s,\quad C_p - C_v = %s" % (num(st["CvR"]), q(st["Cp_minus_Cv"], "J/mol/K")), "Eq. (9), (3)", "", ph["name"])
    step(ctx, "Heat capacities from the equation of state",
         r"C_v = C_p^{ig} - R + C_v^R,\qquad C_p = C_v + (C_p - C_v)",
         r"C_v = %s - %s + %s" % (num(cp_ig), num(R), num(st["CvR"])),
         r"C_p = %s,\quad C_v = %s" % (q(st["Cp"], "J/mol/K"), q(st["Cv"], "J/mol/K")), "Eq. (5)", "", ph["name"])


def _root_request(state):
    return {"gas": "vapour", "liquid": "liquid"}.get(state, "stable")


def m_peng_robinson(ctx, ph, need, with_cp=True):
    comp = ph["substance"]
    Tc, Pc, om = get(ctx, need, comp, "Tc"), get(ctx, need, comp, "Pc"), get(ctx, need, comp, "omega")
    cp_ig = get(ctx, need, comp, "cp_ig", "gas")
    M = get(ctx, need, comp, "M")
    if need["missing"]:
        return None
    T, P = ctx["T"], ctx["P"]
    p = pure.pr_parameters(Tc, Pc, om, T)
    try:
        st = pure.pr_state(T, P, p["a"], p["b"], p["da"], p["d2a"], cp_ig, _root_request(ph["state"]), Tc, Pc)
    except CalcError as err:
        need["missing"] += [("error", e["code"], e["what"]) for e in err.problems]
        return None
    for code, text in st["warnings"]:
        warn(ctx, code, text)
    _pr_flags(ctx, ph, comp, T, Tc, om, st["label"].startswith("liquid"))
    _pr_steps(ctx, ph, comp, p, st, cp_ig)
    return {"cp": st["Cp"] / M, "cv": st["Cv"] / M, "Cp_molar": st["Cp"], "Cv_molar": st["Cv"], "M": M,
            "rho": M / st["v"], "alpha": st["alpha"], "kappa": st["kappa"], "label": st["label"],
            "extra": {"Z": st["Z"], "roots": st["roots"]}}


def m_debye(ctx, ph, need, with_cp=True):
    comp, state = ph["substance"], ph["state"]
    theta = get(ctx, need, comp, "theta_D", state)
    n = get(ctx, need, comp, "n_atoms", state)
    M = get(ctx, need, comp, "M")
    ge = optional(ctx, need, comp, "gamma_e", state)
    rho = alpha = kappa = None
    if with_cp:
        rho, alpha, kappa = (get(ctx, need, comp, k, state) for k in ("rho", "alpha_V", "kappa_T"))
    if need["missing"]:
        return None
    if ge is None:
        ge = 0.0
        assume(ctx, "gamma_e_zero", comp)
    T = ctx["T"]
    Cv = pure.debye_cv(T, theta, n, ge)
    step(ctx, "Debye model for '%s'" % ph["name"],
         r"C_v = 9nR\left(\frac{T}{\theta_D}\right)^{3}\int_0^{\theta_D/T}\frac{x^4e^x}{(e^x-1)^2}\,dx + \gamma_e T",
         r"\theta_D = %s,\; n = %s,\; \gamma_e = %s,\; T/\theta_D = %s" % (q(theta, "K"), num(n), num(ge), num(T / theta, 4)),
         r"C_v = %s\quad (C_v/3nR = %s)" % (q(Cv, "J/mol/K"), num(Cv / (3 * n * R), 4)), "Eq. (13)", "", ph["name"])
    out = {"cv": Cv / M, "Cv_molar": Cv, "M": M, "label": "Debye solid"}
    if with_cp:
        d = pure.cp_minus_cv(T, rho, alpha, kappa)
        out.update({"cp": Cv / M + d, "Cp_molar": (Cv / M + d) * M, "rho": rho, "alpha": alpha, "kappa": kappa})
    return out


PURE_FUNCS = {"data": m_data, "Peng-Robinson": m_peng_robinson, "ideal gas": m_ideal_gas, "Debye": m_debye}


def evaluate_pure(ctx, ph, want):
    b = blank_bundle(ph)
    problems = []
    order = AUTO_PURE[ph["state"]] if ph["method"] == "auto" else [ph["method"]]
    how = "your choice" if ph["method"] != "auto" else "first complete method"
    tries = []
    for method in order:
        need = new_need()
        out = PURE_FUNCS[method](ctx, ph, need, True)
        if out is not None:
            extra = out.pop("extra", {})
            b.update(out)
            b["extra"].update(extra)
            b["method_cp"] = method
            accept(ctx, need)
            break
        tries.append((method, need))
    record_route(ctx, ph, "c_p", tries, b["method_cp"], how)
    if b["cp"] is None and want["cp"]:
        problems.append(missing_problem(ctx, ph, "c_p", tries, ["cp", "cv"] if want["multi"] else ["cp"]))

    if want["cv"] or want["cv_opt"]:
        if b["cv"] is not None:
            b["method_cv"] = b["method_cp"]
        else:
            cv_tries = []
            need = new_need()
            out = cv_identity(ctx, ph, b, need)
            if out is not None:
                b.update(out)
                b["method_cv"] = "c_p-c_v identity"
                accept(ctx, need)
            else:
                cv_tries.append(("c_p-c_v identity", need))
                if ph["state"] == "solid" and b["method_cp"] != "Debye" and ph["method"] == "auto":
                    need = new_need()
                    out = m_debye(ctx, ph, need, with_cp=False)
                    if out is not None:
                        b["cv"], b["Cv_molar"] = out["cv"], out["Cv_molar"]
                        b["M"] = b["M"] or out["M"]
                        b["method_cv"] = "Debye"
                        accept(ctx, need)
                    else:
                        cv_tries.append(("Debye", need))
            record_route(ctx, ph, "c_v", cv_tries, b["method_cv"], "first complete method")
            if b["cv"] is None and want["cv"]:
                problems.append(missing_problem(ctx, ph, "c_v", cv_tries, ["cv"]))
    problems += assembly_data(ctx, ph, b, want)
    return b, problems


def assembly_data(ctx, ph, b, want):
    """rho (Eq. 20 with volume fractions, Eq. 21) and alpha_V, kappa_T (Eq. 21)."""
    probs = []
    jobs = []
    if want["rho"]:
        jobs.append(("rho", "rho", want["rho_for"]))
    if want["ak"]:
        jobs += [("alpha", "alpha_V", ["cv"]), ("kappa", "kappa_T", ["cv"])]
    for slot, key, affects in jobs:
        if b[slot] is not None:
            continue
        need = new_need()
        if ph["is_mixture"]:
            need["missing"].append("%s of each component (needed for the mixture)" % key)
        else:
            v = get(ctx, need, ph["substance"], key, ph["state"])
            if v is not None:
                b[slot] = v
                accept(ctx, need)
                continue
        probs.append(missing_problem(ctx, ph, key, [("sample assembly (Eq. 20, 21)", need)], affects))
    return probs


# ================================================================== 3. mixtures
def get_pair(ctx, need, i, j, key, symmetric=False, required=True):
    for p in ctx["case"]["pairs"]:
        if p["key"] != key:
            continue
        if (p["i"] == i and p["j"] == j) or (symmetric and p["i"] == j and p["j"] == i):
            need["recs"].append({"comp": "%s-%s" % (p["i"], p["j"]), "key": key, "value": p["value"], "unit": "-",
                                 "given": "%g" % p["value"], "kind": p["kind"], "source": p.get("source") or "(no source)",
                                 "route": "yours", "range": (None, None), "note": "", "inputs": []})
            return p["value"]
    if required:
        need["missing"].append("pair parameter %s (%s, %s)" % (key, i, j))
    return None


def _has_pairs(ctx, comps, prefix):
    return any(p["key"].startswith(prefix) and p["i"] in comps and p["j"] in comps for p in ctx["case"]["pairs"])


def mixture_fractions(ctx, ph, mix, need, need_M):
    """x (mole) and w (mass) fractions of the mixture components."""
    comps, state, f = list(mix["components"]), ph["state"], mix["components"]
    M = {c: (get if (need_M or mix["basis"] == "mole") else optional)(ctx, need, c, "M") for c in comps}
    have_M = all(v is not None for v in M.values())
    if mix["basis"] == "mass":
        w = dict(f)
    elif mix["basis"] == "mole":
        w = mx.x_to_w(f, M) if have_M else None
    else:
        rho = {c: get(ctx, need, c, "rho", state) for c in comps}
        w = mx.phi_to_w(f, rho) if all(v is not None for v in rho.values()) else None
    x = (dict(f) if mix["basis"] == "mole" else mx.w_to_x(w, M)) if (have_M and w) else None
    return x, w, (M if have_M else None)


def evaluate_mixture(ctx, ph, want):
    b = blank_bundle(ph)
    mix = ctx["case"]["mixtures"][ph["substance"]]
    comps = list(mix["components"])
    model = mix["model"]
    how = "your choice"
    if model == "auto":
        how = "auto"
        if ph["state"] == "gas":
            ok = all(find(ctx, c, k, s) is not None for c in comps for k, s in
                     (("Tc", ""), ("Pc", ""), ("omega", ""), ("cp_ig", "gas"), ("M", "")))
            model = "Peng-Robinson" if ok else "ideal gas"
        elif _has_pairs(ctx, comps, "nrtl_"):
            model = "NRTL"
        elif _has_pairs(ctx, comps, "marg_"):
            model = "Margules"
        else:
            model = "ideal"
    need, need_cv = new_need(), new_need()
    if model == "Peng-Robinson":
        out = mix_peng_robinson(ctx, ph, mix, need)
    elif model == "ideal gas":
        out = mix_ideal_gas(ctx, ph, mix, need)
    else:
        out = mix_condensed(ctx, ph, mix, model, need, need_cv, want)
    problems = []
    record_route(ctx, ph, "c_p and c_v", [] if out else [(model, need)], model if out else "", how)
    if out is None:
        problems.append(missing_problem(ctx, ph, "c_p", [(model, need)], ["cp", "cv"]))
        return b, problems
    extra = out.pop("extra", {})
    b.update(out)
    b["extra"].update(extra)
    b["method_cp"] = b["method_cv"] = model
    accept(ctx, need)
    if b["cv"] is None:
        b["method_cv"] = ""
        if want["cv"]:
            problems.append(missing_problem(ctx, ph, "c_v", [(model, need_cv)], ["cv"]))
    else:
        accept(ctx, need_cv)
    problems += assembly_data(ctx, ph, b, want)
    return b, problems


def mix_condensed(ctx, ph, mix, model, need, need_cv, want):
    """Ideal, NRTL or Margules liquid (or solid) mixture."""
    comps, state, T, pid = list(mix["components"]), ph["state"], ctx["T"], ph["name"]
    par = None
    if model in ("NRTL", "Margules"):
        if len(comps) != 2:
            need["missing"].append(("error", "E06", "%s is for two components only (this mixture has %d)" % (model, len(comps))))
            return None
        c1, c2 = comps
        if model == "Margules":
            par = {"A": get_pair(ctx, need, c1, c2, "marg_A", True, False) or 0.0,
                   "B": get_pair(ctx, need, c1, c2, "marg_B", True, False) or 0.0,
                   "D": get_pair(ctx, need, c1, c2, "marg_D", True)}
        else:
            par = {"alpha": get_pair(ctx, need, c1, c2, "nrtl_alpha", True)}
            for i, j, tag in ((c1, c2, "12"), (c2, c1, "21")):
                vals = {k: get_pair(ctx, need, i, j, "nrtl_" + k, False, False) for k in ("a", "b", "e")}
                if all(v is None for v in vals.values()):
                    need["missing"].append("NRTL tau parameters for %s -> %s" % (i, j))
                par.update({k + tag: (v or 0.0) for k, v in vals.items()})
    x, w, M = mixture_fractions(ctx, ph, mix, need, need_M=(model != "ideal"))
    cp = {c: get(ctx, need, c, "cp", state) for c in comps}
    if need["missing"] or w is None:
        if w is None and not need["missing"]:
            need["missing"].append("fractions could not be converted")
        return None
    out = {"label": "%s mixture" % model, "extra": {"CpE": 0.0}}
    cp_mix = sum(w[c] * cp[c] for c in comps)
    step(ctx, "Mixture '%s': ideal part" % mix["name"], r"c_p^{id} = \sum_i w_i\,c_{p,i}",
         " + ".join(r"%s\times%s" % (num(w[c], 5), num(cp[c])) for c in comps),
         r"c_p^{id} = %s" % q(cp_mix, "J/kg/K"), "Sec. 3.5, Level 1",
         "mass fractions: " + ", ".join("%s %.5f" % (c, w[c]) for c in comps), pid)
    M_mix = sum(x[c] * M[c] for c in comps) if (x and M) else None
    if model == "ideal":
        assume(ctx, "ce_zero", mix["name"])
    else:
        x1 = x[comps[0]]
        if model == "Margules":
            ge = mx.ge_margules(x1, T, par["A"], par["B"], par["D"])
            he, cpe = mx.margules_he(x1, T, par["B"], par["D"]), mx.margules_cpe(x1, T, par["D"])
            eq = r"\frac{G^E}{RT} = x_1x_2\left(A+\frac{B}{T}+D\ln T\right),\quad H^E = Rx_1x_2(B-DT),\quad C_p^E = -RDx_1x_2"
            sub = r"x_1 = %s,\; A = %s,\; B = %s,\; D = %s" % (num(x1, 5), num(par["A"]), num(par["B"]), num(par["D"]))
            ref = "Eq. (15)"
        else:
            g = lambda TT: mx.ge_nrtl(x1, TT, par)
            ge, he, cpe = g(T), mx.he_from_ge(g, T), mx.cpe_from_ge(g, T)
            eq = (r"\frac{G^E}{RT} = x_1x_2\left[\frac{\tau_{21}G_{21}}{x_1+x_2G_{21}}+\frac{\tau_{12}G_{12}}{x_2+x_1G_{12}}\right],"
                  r"\quad C_p^E = -T\frac{\partial^2 G^E}{\partial T^2}")
            sub = r"x_1 = %s,\; \tau_{12} = %s,\; \tau_{21} = %s,\; \alpha = %s" % (
                num(x1, 5), num(mx.nrtl_tau(par["a12"], par["b12"], par["e12"], T)),
                num(mx.nrtl_tau(par["a21"], par["b21"], par["e21"], T)), num(par["alpha"]))
            ref = "Eq. (14), (16)"
        step(ctx, "Mixture '%s': excess functions (%s)" % (mix["name"], model), eq, sub,
             r"G^E = %s,\; H^E = %s,\; C_p^E = %s" % (q(ge, "J/mol"), q(he, "J/mol"), q(cpe, "J/mol/K")), ref, "", pid)
        if cpe < 0:
            note(ctx, "negative C_p^E in '%s' is legitimate and is not corrected" % mix["name"])
        cp_mix += cpe / M_mix
        out["extra"].update({"CpE": cpe, "HE": he, "GE": ge})
        step(ctx, "Mixture '%s': total" % mix["name"], r"c_p = c_p^{id} + \frac{C_p^E}{M}", "",
             r"c_p = %s" % q(cp_mix, "J/kg/K"), "Eq. (14)", "", pid)
    out.update({"cp": cp_mix, "M": M_mix, "Cp_molar": cp_mix * M_mix if M_mix else None})
    if want["rho"] or want["cv"] or want["cv_opt"] or want["ak"]:
        rho = {c: get(ctx, need_cv, c, "rho", state) for c in comps}
        if all(v is not None for v in rho.values()):
            alpha = {c: get(ctx, need_cv, c, "alpha_V", state) for c in comps}
            kappa = {c: get(ctx, need_cv, c, "kappa_T", state) for c in comps}
            ok = all(v is not None for v in list(alpha.values()) + list(kappa.values()))
            vp = mx.ideal_volume(w, rho, alpha if ok else None, kappa if ok else None)
            assume(ctx, "ve_zero", mix["name"])
            out["rho"] = vp["rho"]
            step(ctx, "Mixture '%s': density (V^E = 0)" % mix["name"], r"\frac{1}{\rho} = \sum_i \frac{w_i}{\rho_i}",
                 " + ".join(r"\frac{%s}{%s}" % (num(w[c], 5), num(rho[c])) for c in comps),
                 r"\rho = %s" % q(vp["rho"], "kg/m3"), "", "", pid)
            if ok:
                d = mx.cp_minus_cv_mixture(T, w, rho, alpha, kappa)
                out.update({"alpha": vp["alpha"], "kappa": vp["kappa"], "cv": cp_mix - d})
                if M_mix:
                    out["Cv_molar"] = out["cv"] * M_mix
                naive = sum(w[c] * (cp[c] - pure.cp_minus_cv(T, rho[c], alpha[c], kappa[c])) for c in comps)
                out["extra"]["sum_w_cv_i"] = naive
                step(ctx, "Mixture '%s': c_v" % mix["name"],
                     r"c_p - c_v = \frac{T\left(\sum_i w_i\alpha_i/\rho_i\right)^2}{\sum_i w_i\kappa_i/\rho_i}",
                     r"c_p - c_v = %s" % q(d, "J/kg/K"),
                     r"c_v = %s\quad\left(\text{naive } \sum_i w_i c_{v,i} = %s\right)" % (q(out["cv"], "J/kg/K"), num(naive)),
                     "Eq. (19)", "c_v of a mixture is not the mass average of the c_v of its components", pid)
    return out


def mix_peng_robinson(ctx, ph, mix, need):
    comps, T, P = list(mix["components"]), ctx["T"], ctx["P"]
    x, w, M = mixture_fractions(ctx, ph, mix, need, need_M=True)
    pars, cp_ig, crit = {}, {}, {}
    for c in comps:
        Tc, Pc, om = get(ctx, need, c, "Tc"), get(ctx, need, c, "Pc"), get(ctx, need, c, "omega")
        cp_ig[c] = get(ctx, need, c, "cp_ig", "gas")
        if None not in (Tc, Pc, om):
            pars[c], crit[c] = pure.pr_parameters(Tc, Pc, om, T), (Tc, om)
    kij = {}
    for a in range(len(comps)):
        for b in range(a + 1, len(comps)):
            k = get_pair(ctx, need, comps[a], comps[b], "kij", True, False)
            if k is None:
                k = 0.0
                assume(ctx, "kij_zero", "%s-%s" % (comps[a], comps[b]))
            kij[(comps[a], comps[b])] = k
    if need["missing"] or x is None:
        return None
    m = mx.mix_pr(x, pars, kij)
    cpig = sum(x[c] * cp_ig[c] for c in comps)
    try:
        st = pure.pr_state(T, P, m["a"], m["b"], m["da"], m["d2a"], cpig, _root_request(ph["state"]))
    except CalcError as err:
        need["missing"] += [("error", e["code"], e["what"]) for e in err.problems]
        return None
    for code, text in st["warnings"]:
        warn(ctx, code, text)
    warn(ctx, "A07", "mixture '%s': stability not checked (phase splitting is not detected)" % mix["name"])
    for c in comps:
        _pr_flags(ctx, ph, c, T, crit[c][0], crit[c][1], st["label"].startswith("liquid"))
    step(ctx, "Mixture '%s': one-fluid mixing rule" % mix["name"],
         r"a_m = \sum_i\sum_j x_ix_j(1-k_{ij})\sqrt{a_ia_j},\quad b_m = \sum_i x_ib_i,\quad C_p^{ig} = \sum_i x_iC_{p,i}^{ig}",
         ",\\ ".join(r"x_{\text{%s}} = %s" % (c, num(x[c], 5)) for c in comps),
         r"C_p^{ig} = %s" % q(cpig, "J/mol/K"), "Eq. (17)-(18)", "", ph["name"])
    _pr_steps(ctx, ph, "mixture", m, st, cpig)
    Mm = sum(x[c] * M[c] for c in comps)
    return {"cp": st["Cp"] / Mm, "cv": st["Cv"] / Mm, "Cp_molar": st["Cp"], "Cv_molar": st["Cv"], "M": Mm,
            "rho": Mm / st["v"], "alpha": st["alpha"], "kappa": st["kappa"], "label": "mixture, " + st["label"],
            "extra": {"Z": st["Z"], "roots": st["roots"]}}


def mix_ideal_gas(ctx, ph, mix, need):
    comps, T, P = list(mix["components"]), ctx["T"], ctx["P"]
    x, w, M = mixture_fractions(ctx, ph, mix, need, need_M=True)
    cp_ig = {c: get(ctx, need, c, "cp_ig", "gas") for c in comps}
    if need["missing"] or x is None:
        return None
    Cp = sum(x[c] * cp_ig[c] for c in comps)
    Mm = sum(x[c] * M[c] for c in comps)
    step(ctx, "Mixture '%s' as an ideal gas" % mix["name"], r"C_p = \sum_i x_i C_{p,i}^{ig},\qquad C_v = C_p - R",
         " + ".join(r"%s\times%s" % (num(x[c], 5), num(cp_ig[c])) for c in comps),
         r"C_p = %s,\quad C_v = %s" % (q(Cp, "J/mol/K"), q(Cp - R, "J/mol/K")), "Eq. (5), (17)", "", ph["name"])
    return {"cp": Cp / Mm, "cv": (Cp - R) / Mm, "Cp_molar": Cp, "Cv_molar": Cp - R, "M": Mm,
            "rho": P * Mm / (R * T), "alpha": 1.0 / T, "kappa": 1.0 / P, "label": "ideal-gas mixture"}


# ================================================================== 4. explaining what is missing
def missing_problem(ctx, ph, quantity, tries, affects):
    lines, codes, keys, hints = [], [], [], []
    for method, need in tries:
        parts = []
        for m in need["missing"]:
            parts.append(_missing_text(ph, m))
            if isinstance(m, tuple) and m[0] == "error":
                codes.append(m[1])
            elif isinstance(m, tuple):
                codes.append("E04" if ctx["out_of_range"].get(m) else "E01")
                if m not in keys:
                    keys.append(m)
            else:
                codes.append("E01")
        lines.append("%s needs: %s" % (method, ", ".join(parts) or "-"))
    for comp, key, state in keys:
        tried = ctx["tried"].get((comp, key, state), [])
        lines.append("%s of %s: %s" % (key, comp, "; ".join(tried) or "not found"))
        hint = _phase_change_hint(ctx, comp, state, (comp, key, state))
        if hint and hint not in lines:
            lines.append(hint)
        if database.entry(ctx["db"], comp) is None and not any(r["component"] == comp for r in ctx["case"]["data"]):
            hints.append("%s is not in the database: add its data, or use 'Find a compound'" % comp)
        if key in WHERE_TO_LOOK:
            hints.append("%s: %s" % (key, WHERE_TO_LOOK[key]))
    code = "E04" if "E04" in codes else ("E01" if "E01" in codes or not codes else codes[0])
    pr = problem(code, "", "", lines, affects)
    pr.update({"phase": ph["name"], "quantities": [quantity], "hints": hints,
               "label": "phase '%s' (%s, %s) at %.2f K" % (ph["name"], ph["substance"], ph["state"], ctx["T"])})
    return pr


def merge_problems(problems):
    """One message per phase: everything that phase is missing, in one place."""
    merged, order = {}, []
    for p in problems:
        key = p.get("phase") or id(p)
        if key not in merged:
            merged[key] = dict(p, lines=list(p["lines"]), affects=list(p["affects"]),
                               quantities=list(p.get("quantities", [])), hints=list(p.get("hints", [])))
            order.append(key)
            continue
        m = merged[key]
        m["lines"] += [l for l in p["lines"] if l not in m["lines"]]
        m["affects"] = sorted(set(m["affects"]) | set(p["affects"]))
        m["quantities"] += [q_ for q_ in p.get("quantities", []) if q_ not in m["quantities"]]
        m["hints"] += [h for h in p.get("hints", []) if h not in m["hints"]]
    out = []
    for key in order:
        m = merged[key]
        if m.get("phase"):
            m["what"] = "cannot get %s of %s" % (", ".join(m["quantities"]), m["label"])
            m["fix"] = "Give the missing values for any ONE of the methods listed."
            if m["hints"]:
                m["fix"] += " Where to look: " + "; ".join(dict.fromkeys(m["hints"])) + "."
            if "E04" in [m["code"]] or any("valid " in l for l in m["lines"]):
                m["fix"] += " Data are never extrapolated: change T or give values valid at this T."
        out.append(m)
    return out


def _phase_change_hint(ctx, comp, state, ck):
    if not ctx["out_of_range"].get(ck) or state != "liquid":
        return ""
    tm, tb = find(ctx, comp, "T_melt"), find(ctx, comp, "T_boil")
    T = ctx["T"]
    if tb and T > tb["value"]:
        return "%s boils at %.2f K at 1 atm: at %.2f K it is not a liquid at 1 atm" % (comp, tb["value"], T)
    if tm and T < tm["value"]:
        return "%s melts at %.2f K: at %.2f K it is a solid" % (comp, tm["value"], T)
    return ""


# ================================================================== 5. the whole sample
def run_case(case, db=None):
    db = db if db is not None else database.load_database()
    case = check_case(case, db)
    ctx = new_context(case, db)
    for code, text in case["_warnings"]:
        warn(ctx, code, text)
    T, P = case["T"], case["P"]
    step(ctx, "Conditions", "", r"T = %s,\quad P = %s" % (q(T, "K"), q(P, "Pa")), "", "",
         "%d phase(s), amounts as %s fractions" % (len(case["phases"]), case["basis"]))
    if abs(P - P_ATM) > 5e5 and any(p["state"] != "gas" for p in case["phases"]):
        note(ctx, "database liquid data are at 1 atm; at %.3g bar the pressure effect on liquids is neglected" % (P / 1e5))
    active = [p for p in case["phases"] if p["amount"] > 0]
    multi = len(active) > 1
    want_cp, want_cv = case["quantity"] in ("cp", "both"), case["quantity"] in ("cv", "both")
    volume = case["basis"] == "volume"
    bundles, problems = {}, []
    for ph in active:
        want = {"cp": want_cp or (want_cv and multi), "cv": want_cv and not multi, "cv_opt": want_cv and multi,
                "rho": multi and (volume or want_cv), "rho_for": ["cp", "cv"] if volume else ["cv"],
                "ak": want_cv and multi, "multi": multi}
        b, probs = (evaluate_mixture if ph["is_mixture"] else evaluate_pure)(ctx, ph, want)
        bundles[ph["name"]] = b
        problems += probs
    problems = merge_problems(problems)
    blocked = set(a for p in problems for a in p["affects"])
    out = assemble(ctx, case, active, bundles, want_cp and "cp" not in blocked,
                   want_cv and "cv" not in blocked)
    return build_result(ctx, case, active, bundles, out, problems, want_cp, want_cv)


def assemble(ctx, case, active, bundles, can_cp, can_cv):
    T = case["T"]
    names = [p["name"] for p in active]
    multi = len(names) > 1
    out = {"cp_app": None, "cv_app": None, "w": {}, "phi": {}, "rho_s": None, "checks": [], "diag": {}}
    rho = {k: bundles[k]["rho"] for k in names}
    have_rho = all(v is not None for v in rho.values())
    amount = {p["name"]: p["amount"] for p in active}
    if not multi:
        out["w"], out["phi"], out["rho_s"] = {names[0]: 1.0}, {names[0]: 1.0}, rho[names[0]]
    elif case["basis"] == "volume":
        out["phi"] = dict(amount)
        if have_rho:
            out["w"], out["rho_s"] = sample.volume_to_mass(amount, rho)
            step(ctx, "Phase mass fractions", r"w_k = \frac{\phi_k\rho_k}{\sum_j \phi_j\rho_j}",
                 r"\rho_s = " + " + ".join(r"%s\times%s" % (num(amount[k], 5), num(rho[k])) for k in names)
                 + " = " + q(out["rho_s"], "kg/m3"),
                 r",\ ".join(r"w_{\text{%s}} = %s" % (k, num(out["w"][k], 5)) for k in names), "Eq. (20)")
    else:
        out["w"] = dict(amount)
        if have_rho:
            out["phi"], out["rho_s"] = sample.mass_to_volume(amount, rho)
    for p in case["phases"]:
        if p["amount"] == 0:
            out["w"].setdefault(p["name"], 0.0)
            out["phi"].setdefault(p["name"], 0.0)
    pw = case.get("phi_warn", 0.60)
    if multi and out["phi"] and pw:
        disp = sum(out["phi"][p["name"]] for p in active if p["role"] == "dispersed")
        if disp >= pw:
            warn(ctx, "A03", "dispersed volume fraction %.3f >= %.2f (packing limits depend on the system)" % (disp, pw))
    w = {k: out["w"].get(k) for k in names}
    cp = {k: bundles[k]["cp"] for k in names}
    if (can_cp or (can_cv and multi)) and None not in w.values() and None not in cp.values():
        out["cp_app"] = sample.cp_apparent(w, cp)
        if multi:
            step(ctx, "Apparent c_p of the sample (thermal equilibrium, mass-weighted)",
                 r"c_{p,\mathrm{app}} = \sum_k w_k\,c_{p,k}",
                 " + ".join(r"%s\times%s" % (num(w[k], 5), num(cp[k])) for k in names),
                 r"c_{p,\mathrm{app}} = %s" % q(out["cp_app"], "J/kg/K"), "Eq. (2), (20)")
    if can_cv:
        if not multi:
            out["cv_app"] = bundles[names[0]]["cv"]
        elif out["cp_app"] is not None:
            phi = {k: out["phi"][k] for k in names}
            al = {k: bundles[k]["alpha"] for k in names}
            ka = {k: bundles[k]["kappa"] for k in names}
            d = sample.cp_minus_cv_sample(T, phi, al, ka, out["rho_s"])
            out["cv_app"] = out["cp_app"] - d
            out["diag"]["cp_minus_cv"] = d
            step(ctx, "Apparent c_v of the sample (whole-sample identity)",
                 r"c_{p,\mathrm{app}} - c_{v,\mathrm{app}} = \frac{T\left(\sum_k \phi_k\alpha_k\right)^2}{\rho_s\sum_k \phi_k\kappa_k}",
                 r"= \frac{%s\times(%s)^2}{%s\times%s} = %s" % (num(T), num(sum(phi[k] * al[k] for k in names)),
                                                               num(out["rho_s"]), num(sum(phi[k] * ka[k] for k in names)),
                                                               q(d, "J/kg/K")),
                 r"c_{v,\mathrm{app}} = %s" % q(out["cv_app"], "J/kg/K"), "Eq. (21)",
                 "c_v of a sample is NOT the mass average of the phase c_v: at constant total volume the phases exchange volume")
            cvk = {k: bundles[k]["cv"] for k in names}
            if None not in cvk.values():
                naive = sum(w[k] * cvk[k] for k in names)
                gap = sample.cv_gap(T, phi, al, ka, out["rho_s"])
                out["diag"].update({"sum_w_cv": naive, "gap": out["cv_app"] - naive, "gap_eq23": gap})
                step(ctx, "Check: lower bound and gap", r"c_{v,\mathrm{app}} \geq \sum_k w_k c_{v,k}",
                     r"\sum_k w_k c_{v,k} = %s" % q(naive, "J/kg/K"),
                     r"\text{gap} = %s\ (\text{Eq. 23: } %s)" % (num(out["cv_app"] - naive), num(gap)), "Eq. (22), (23)")
    if out["cp_app"] is not None and multi and out["phi"] and None not in out["phi"].values():
        vw = sample.cp_volume_weighted({k: out["phi"][k] for k in names}, cp)
        out["diag"]["volume_weighted"] = vw
        out["diag"]["volume_weighted_pct"] = 100 * (vw / out["cp_app"] - 1)
    _checks(out, bundles, names, multi)
    if not can_cp:
        out["cp_app_internal"], out["cp_app"] = out["cp_app"], None
    return out


def _checks(out, bundles, names, multi):
    ch = out["checks"]
    if out["w"] and None not in [out["w"].get(k) for k in names]:
        ch.append(("sum of w = 1", abs(sum(out["w"][k] for k in names) - 1) < 1e-9))
    cp, cv = out["cp_app"], out["cv_app"]
    if cp is not None and multi:
        cps = [bundles[k]["cp"] for k in names]
        ch.append(("min c_p,k <= c_p,app <= max c_p,k", min(cps) - 1e-9 <= cp <= max(cps) + 1e-9))
    if cv is not None:
        ch.append(("c_v,app > 0", cv > 0))
        if cv <= 0:
            raise CalcError(problem("E07", "c_v,app = %.4g J/kg/K is not positive" % cv, "check alpha_V, kappa_T and rho"))
    if cp is not None and cv is not None:
        ch.append(("c_p,app >= c_v,app", cp >= cv - 1e-9))
    if "sum_w_cv" in out["diag"]:
        ch.append(("c_v,app >= sum w c_v,k (Eq. 22)", out["diag"]["gap"] >= -1e-9))
        ch.append(("gap equals Eq. 23", abs(out["diag"]["gap"] - out["diag"]["gap_eq23"]) <= 1e-6 * max(1.0, abs(cv))))


def _status(ctx, has_problem, kinds):
    if has_problem:
        return "not calculable", ["missing or unusable data (see the errors)"]
    reasons = []
    wk = weakest(kinds) if kinds else "experimental"
    if wk not in ("experimental", "derived"):
        reasons.append("weakest input kind: %s" % wk)
    reasons += ["%s %s" % (w["code"], w["text"]) for w in ctx["warnings"]]
    reasons += ["assumption: %s (%s)" % (ASSUMPTIONS[a["name"]], a["detail"]) for a in ctx["assumptions"]]
    return ("calculated under assumptions" if reasons else "calculated"), reasons


def build_result(ctx, case, active, bundles, out, problems, want_cp, want_cv):
    if ctx["illustrative"]:
        warn(ctx, "A08", "illustrative data in use: " + ", ".join(ctx["illustrative"]))
    kinds = [u["kind"] for u in ctx["used"]]
    results = {}
    for q_, key, wanted in (("cp", "cp_app", want_cp), ("cv", "cv_app", want_cv)):
        if not wanted:
            continue
        bad = any(q_ in p["affects"] for p in problems) or out[key] is None
        if out[key] is None and not any(q_ in p["affects"] for p in problems):
            problems.append(problem("E01", "%s could not be assembled" % key, "", [], [q_]))
        status, reasons = _status(ctx, bad, kinds)
        results[key] = {"value": None if bad else out[key], "status": status, "reasons": reasons}
    statuses = [r["status"] for r in results.values()]
    if all(s == "calculated" for s in statuses):
        overall = "calculated"
    elif all(s == "not calculable" for s in statuses):
        overall = "not calculable"
    elif "not calculable" in statuses:
        overall = "partly calculable"
    else:
        overall = "calculated under assumptions"
    phases = []
    for p in case["phases"]:
        b = bundles.get(p["name"], blank_bundle(p))
        phases.append(dict(b, w=out["w"].get(p["name"]), phi=out["phi"].get(p["name"]), amount=p["amount"]))
    molar = {}
    if len(active) == 1:
        M = bundles[active[0]["name"]]["M"]
        if M is None and not active[0]["is_mixture"]:
            m = find(ctx, active[0]["substance"], "M")
            M = m["value"] if m else None
        for key, name in (("cp_app", "Cp"), ("cv_app", "Cv")):
            if M and key in results and results[key]["value"] is not None:
                molar[name] = results[key]["value"] * M
    return {
        "name": case["name"], "T": case["T"], "P": case["P"], "quantity": case["quantity"], "basis": case["basis"],
        "status": overall, "results": results, "molar": molar, "phases": phases, "rho_s": out["rho_s"],
        "checks": [{"name": n, "ok": ok} for n, ok in out["checks"]], "diagnostics": out["diag"],
        "warnings": ctx["warnings"], "notes": ctx["notes"], "problems": problems,
        "assumptions": {"standing": STANDING_ASSUMPTIONS,
                        "used": [dict(a, text=ASSUMPTIONS[a["name"]]) for a in ctx["assumptions"]]},
        "provenance": [{k: u[k] for k in ("comp", "key", "value", "unit", "given", "kind", "route", "source", "range", "note")}
                       for u in ctx["used"]],
        "illustrative": bool(ctx["illustrative"]), "steps": ctx["steps"], "routes": ctx["routes"],
        "mixtures": {k: v for k, v in case["mixtures"].items()}, "version": VERSION,
    }


# ================================================================== 6. sweeps
def sweep_values(start, stop, n):
    n = max(2, int(n))
    return [start + (stop - start) * i / (n - 1) for i in range(n)]


def run_sweep(case, db=None):
    """case["sweep"] = {"variable": "T" | "phi" | "x", "start", "stop", "n", "target"}.
    phi: amount of phase 'target' (others scaled); x: fraction of the first component of mixture 'target'."""
    db = db if db is not None else database.load_database()
    sw = case["sweep"]
    points = []
    for v in sweep_values(float(sw["start"]), float(sw["stop"]), sw.get("n", 11)):
        c = copy.deepcopy(case)
        c.pop("sweep", None)
        if sw["variable"] == "T":
            c["T"] = v
        elif sw["variable"] == "phi":
            others = [p for p in c["phases"] if p["name"] != sw["target"]]
            rest = sum(float(p["amount"]) for p in others)
            for p in c["phases"]:
                p["amount"] = v if p["name"] == sw["target"] else (float(p["amount"]) / rest * (1 - v) if rest else 0.0)
        elif sw["variable"] == "x":
            key = [k for k in c["mixtures"] if k.lower() == str(sw["target"]).lower()][0]
            comps = c["mixtures"][key]["components"]
            names = list(comps)
            rest = sum(float(comps[n]) for n in names[1:])
            comps[names[0]] = v
            for n in names[1:]:
                comps[n] = float(comps[n]) / rest * (1 - v) if rest else (1 - v) / (len(names) - 1)
        try:
            points.append({"x": v, "result": run_case(c, db), "error": None})
        except CalcError as err:
            points.append({"x": v, "result": None, "error": err.problems})
    return {"variable": sw["variable"], "target": sw.get("target"), "points": points}

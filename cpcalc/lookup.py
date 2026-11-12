"""Find property data for (almost) any compound with the open-source `thermo` library.

Interface helper only: the engine never imports this module. It is used
(1) by tools/build_database.py to pre-build the database, and
(2) by the UI button "Find a compound" to add a compound that is not built in.

Every record keeps the name of the data method and a citation. Values from
estimation methods (group contribution, corresponding states) are labelled
kind = "estimated"; fitted experimental data are labelled "experimental".
"""

P_ATM = 101325.0

# data method -> (citation, kind)
METHOD_INFO = {
    "COOLPROP": ("CoolProp reference equation of state", "experimental"),
    "HEOS_FIT": ("fit to the CoolProp reference equation of state", "experimental"),
    "HEOS": ("CoolProp reference equation of state", "experimental"),
    "ZABRANSKY_SPLINE_C": ("Zabransky et al., Heat Capacity of Liquids: Critical Review and Recommended Values (1996, 2001)", "experimental"),
    "ZABRANSKY_SPLINE_SAT": ("Zabransky et al., Heat Capacity of Liquids (saturation line, 1996, 2001)", "experimental"),
    "ZABRANSKY_QUASIPOLYNOMIAL_C": ("Zabransky et al., Heat Capacity of Liquids (quasi-polynomial, 1996, 2001)", "experimental"),
    "ZABRANSKY_QUASIPOLYNOMIAL_SAT": ("Zabransky et al., Heat Capacity of Liquids (quasi-polynomial, sat., 1996, 2001)", "experimental"),
    "VDI_TABULAR": ("VDI Heat Atlas, 2nd ed. (2010), tabulated data", "experimental"),
    "VDI_PPDS": ("VDI Heat Atlas, 2nd ed. (2010), PPDS equation", "experimental"),
    "DIPPR_PERRY_8E": ("Perry's Chemical Engineers' Handbook, 8th ed. (DIPPR equations)", "experimental"),
    "POLING_CONST": ("Poling, Prausnitz & O'Connell, The Properties of Gases and Liquids, 5th ed.", "experimental"),
    "POLING_POLY": ("Poling, Prausnitz & O'Connell, The Properties of Gases and Liquids, 5th ed.", "experimental"),
    "TRCIG": ("TRC Thermodynamic Tables ideal-gas heat-capacity correlation", "experimental"),
    "CRCSTD": ("CRC Handbook of Chemistry and Physics, standard thermodynamic properties (298.15 K)", "experimental"),
    "JANAF": ("NIST-JANAF Thermochemical Tables (Chase, 1998)", "experimental"),
    "WEBBOOK_SHOMATE": ("NIST Chemistry WebBook, Shomate equation", "experimental"),
    "PERRY151": ("Perry's Chemical Engineers' Handbook, Table 2-151 (inorganic solids)", "experimental"),
    "UNARY": ("SGTE unary database (Dinsdale, 1991)", "experimental"),
    "CRC_INORG_S": ("CRC Handbook of Chemistry and Physics, physical constants of inorganic compounds", "experimental"),
    "CRC_INORG_L": ("CRC Handbook of Chemistry and Physics, liquid densities of inorganic compounds", "experimental"),
    "CRC_INORG_L_CONST": ("CRC Handbook of Chemistry and Physics, liquid density (constant)", "experimental"),
    "IUPAC": ("IUPAC critical-property reviews (Ambrose, Tsonopoulos et al.)", "experimental"),
    "MATTHEWS": ("Matthews (1972), critical constants of inorganic substances", "experimental"),
    "CRC": ("CRC Handbook of Chemistry and Physics, critical constants", "experimental"),
    "PSRK": ("PSRK parameter table (Horstmann et al., 2005)", "experimental"),
    "WEBBOOK": ("NIST Chemistry WebBook", "experimental"),
    "PINAMARTINES": ("Pina-Martinez et al. (2019), DIPPR-based critical data", "experimental"),
    "LK": ("Lee-Kesler acentric-factor estimate", "estimated"),
    "DEFINITION": ("definition of the acentric factor from vapour pressure", "experimental"),
    "YAWS": ("Yaws' Handbook of thermodynamic properties (may contain estimates)", "estimated"),
    "ROWLINSON_POLING": ("Rowlinson-Poling corresponding-states estimate", "estimated"),
    "ROWLINSON_BONDI": ("Rowlinson-Bondi corresponding-states estimate", "estimated"),
    "DADGOSTAR_SHAW": ("Dadgostar-Shaw estimate", "estimated"),
    "JOBACK": ("Joback group-contribution estimate", "estimated"),
    "LASTOVKA_SHAW": ("Lastovka-Shaw estimate", "estimated"),
    "LASTOVKA_S": ("Lastovka solid heat-capacity estimate", "estimated"),
    "YAMADA_GUNN": ("Yamada-Gunn (Rackett) density estimate", "estimated"),
    "BHIRUD_NORMAL": ("Bhirud density estimate", "estimated"),
    "RACKETTFIT": ("Rackett equation with fitted parameters", "estimated"),
    "HTCOSTALDFIT": ("COSTALD with fitted parameters", "estimated"),
    "COSTALD": ("COSTALD density estimate", "estimated"),
    "COSTALD_COMPRESSED": ("COSTALD compressed-liquid estimate (Thomson, Brobst & Hankinson)", "estimated"),
    "WILSON_JASPERSON": ("Wilson-Jasperson critical-property estimate", "estimated"),
}

CP_LIQ = ["COOLPROP", "HEOS_FIT", "ZABRANSKY_SPLINE_C", "ZABRANSKY_QUASIPOLYNOMIAL_C", "ZABRANSKY_SPLINE_SAT",
          "ZABRANSKY_QUASIPOLYNOMIAL_SAT", "VDI_TABULAR", "DIPPR_PERRY_8E", "POLING_CONST", "CRCSTD",
          "ROWLINSON_POLING", "DADGOSTAR_SHAW"]
CP_GAS = ["COOLPROP", "HEOS_FIT", "TRCIG", "POLING_POLY", "WEBBOOK_SHOMATE", "JANAF", "VDI_TABULAR",
          "POLING_CONST", "CRCSTD", "LASTOVKA_SHAW", "JOBACK"]
CP_SOL = ["JANAF", "WEBBOOK_SHOMATE", "PERRY151", "UNARY", "CRCSTD", "LASTOVKA_S"]
V_LIQ = ["COOLPROP", "HEOS_FIT", "DIPPR_PERRY_8E", "VDI_PPDS", "VDI_TABULAR", "CRC_INORG_L", "CRC_INORG_L_CONST",
         "RACKETTFIT", "HTCOSTALDFIT", "COSTALD", "YAMADA_GUNN", "BHIRUD_NORMAL"]
V_SOL = ["CRC_INORG_S"]

ASSOCIATING_WORDS = ("water", "anol", "diol", "glycol", "glycerol", "acid", "amine", "phenol", "alcohol")


def _info(method, version):
    cite, kind = METHOD_INFO.get(method, ("thermo method %s" % method, "estimated"))
    return "%s [thermo %s, method %s]" % (cite, version, method), kind


def _pick(obj, preference):
    """Choose the first preferred method that is available; returns (method, (Tmin, Tmax))."""
    available = set(obj.all_methods)
    for m in preference:
        if m in available:
            lim = obj.T_limits.get(m)
            if lim and lim[1] > lim[0]:
                return m, lim
    return None, None


def _grid(lo, hi, n=36, extra=(298.15,)):
    if hi <= lo:
        return []
    step = (hi - lo) / (n - 1)
    pts = [lo + i * step for i in range(n)]
    for t in list(extra) + [25.0 * k for k in range(int(lo // 25) + 1, int(hi // 25) + 1)]:
        if lo < t < hi:
            pts.append(t)
    return sorted(set(round(t, 4) for t in pts))


def _curve(key, state, unit, points, method, version, note=""):
    src, kind = _info(method, version)
    return {"key": key, "state": state, "unit": unit, "points": points, "kind": kind, "source": src, "note": note}


def _const(key, value, unit, method, version):
    src, kind = _info(method, version)
    return {"key": key, "value": value, "unit": unit, "kind": kind, "source": src}


def harvest(query, include=("liquid", "gas", "solid")):
    """Return a database entry for a compound name, CAS number or formula.
    Raises LookupError if thermo is not installed or the compound is unknown."""
    try:
        import thermo
        from thermo import Chemical
        import chemicals
    except ImportError:
        raise LookupError("the 'thermo' library is not installed (pip install thermo)")
    try:
        c = Chemical(query)
    except Exception as exc:
        raise LookupError("'%s' was not found in the thermo/chemicals databank (%s)" % (query, exc))
    ver = thermo.__version__
    recs = []
    recs.append({"key": "M", "value": c.MW / 1000.0, "unit": "kg/mol", "kind": "derived",
                 "source": "molar mass from formula %s and IUPAC atomic weights [chemicals]" % c.formula})
    fluid = "liquid" in include or "gas" in include
    for key, func, mfunc, unit in [] if not fluid else [("Tc", chemicals.Tc, chemicals.critical.Tc_methods, "K"),
                                   ("Pc", chemicals.Pc, chemicals.critical.Pc_methods, "Pa"),
                                   ("omega", chemicals.omega, chemicals.acentric.omega_methods, "-")]:
        try:
            methods = mfunc(c.CAS)
            if methods:
                val = func(c.CAS, method=methods[0])
                if val:
                    recs.append(_const(key, float(val), unit, methods[0], ver))
        except Exception:
            pass
    if c.Tm:
        recs.append({"key": "T_melt", "value": float(c.Tm), "unit": "K", "kind": "experimental",
                     "source": "melting point [chemicals %s]" % chemicals.__version__})
    if c.Tb:
        recs.append({"key": "T_boil", "value": float(c.Tb), "unit": "K", "kind": "experimental",
                     "source": "normal boiling point [chemicals %s]" % chemicals.__version__})

    if "liquid" in include:
        recs += _liquid_records(c, ver)
    if "gas" in include:
        m, lim = _pick(c.HeatCapacityGas, CP_GAS)
        if m:
            c.HeatCapacityGas.method = m
            lo, hi = max(lim[0], 150.0), min(lim[1], 1500.0)
            pts = [[T, c.HeatCapacityGas.T_dependent_property(T)] for T in _grid(lo, hi, 40, (298.15, 300.0, 400.0))]
            pts = [p for p in pts if p[1]]
            if len(pts) >= 2:
                recs.append(_curve("cp_ig", "gas", "J/mol/K", pts, m, ver))
    if "solid" in include:
        recs += _solid_records(c, ver)

    name = (c.name or query).strip()
    low = name.lower()
    return {"name": name[:1].upper() + name[1:], "cas": c.CAS, "formula": c.formula, "aliases": [query.lower()],
            "associating": any(w in low for w in ASSOCIATING_WORDS) or low.endswith("ol"),
            "origin": "thermo %s" % ver, "records": recs}


def _liquid_records(c, ver):
    recs = []
    cp_obj, vl = c.HeatCapacityLiquid, c.VolumeLiquid
    m_cp, lim_cp = _pick(cp_obj, CP_LIQ)
    m_v, lim_v = _pick(vl, V_LIQ)
    lo, hi = c.Tm or 0.0, (c.Tb or 1e9)
    note = "liquid at 101325 Pa, between the melting and the normal boiling point"
    if m_cp:
        cp_obj.method = m_cp
        a, b = max(lim_cp[0], lo), min(lim_cp[1], hi - 0.05)
        pts = [[T, cp_obj.T_dependent_property(T)] for T in _grid(a, b)]
        pts = [p for p in pts if p[1]]
        if len(pts) >= 2:
            recs.append(_curve("cp", "liquid", "J/mol/K", pts, m_cp, ver, note))
    if m_v:
        vl.method = m_v
        a, b = max(lim_v[0], lo) + 0.5, min(lim_v[1], hi - 0.05) - 0.5
        grid = _grid(a, b)
        rho, alpha = [], []
        for T in grid:
            V = vl.T_dependent_property(T)
            V1, V2 = vl.T_dependent_property(T - 0.5), vl.T_dependent_property(T + 0.5)
            if V and V1 and V2:
                rho.append([T, c.MW / 1000.0 / V])
                alpha.append([T, (V2 - V1) / (1.0 * V)])
        if len(rho) >= 2:
            recs.append(_curve("rho", "liquid", "kg/m3", rho, m_v, ver, note))
            src, kind = _info(m_v, ver)
            recs.append({"key": "alpha_V", "state": "liquid", "unit": "1/K", "points": alpha,
                         "kind": "derived" if kind == "experimental" else kind,
                         "source": "alpha_V = (1/V) dV/dT of: " + src, "note": note})
        try:
            vl.method_P = "COOLPROP" if "COOLPROP" in vl.all_methods_P else "COSTALD_COMPRESSED"
            kap = []
            for T in grid:
                Va = vl.TP_dependent_property(T, 101325.0 - 5e4)
                Vb = vl.TP_dependent_property(T, 101325.0 + 5e4)
                V0 = vl.TP_dependent_property(T, 101325.0)
                if Va and Vb and V0 and Va > Vb:
                    kap.append([T, (Va - Vb) / (1e5 * V0)])
            if len(kap) >= 2:
                recs.append(_curve("kappa_T", "liquid", "1/Pa", kap, vl.method_P, ver, note))
        except Exception:
            pass
    return recs


def _solid_records(c, ver):
    recs = []
    cs = c.HeatCapacitySolid
    m, lim = _pick(cs, CP_SOL)
    if m:
        cs.method = m
        a, b = max(lim[0], 100.0), min(lim[1], (c.Tm or 1e9) - 1.0, 1500.0)
        pts = [[T, cs.T_dependent_property(T)] for T in _grid(a, b, 40, (298.15, 300.0))]
        pts = [p for p in pts if p[1]]
        if len(pts) >= 2:
            recs.append(_curve("cp", "solid", "J/mol/K", pts, m, ver))
    vs = c.VolumeSolid
    m, lim = _pick(vs, V_SOL)
    if m:
        vs.method = m
        V = vs.T_dependent_property(298.15)
        if V:
            src, kind = _info(m, ver)
            recs.append({"key": "rho", "state": "solid", "value": c.MW / 1000.0 / V, "unit": "kg/m3", "kind": kind,
                         "source": src, "note": "room-temperature density; used as T-independent"})
    return recs

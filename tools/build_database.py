"""Build cpcalc/data/database.json (developer tool; the engine only reads the JSON).

Sources, in order of preference for a compound found in more than one:
  1. CoolProp reference equations of state (about 130 pure fluids): constants and
     liquid c_p, rho, alpha_V, kappa_T at 101325 Pa between the triple and normal
     boiling points, plus the ideal-gas C_p.
  2. thermo/chemicals (Caleb Bell): evaluated data methods (Zabransky, DIPPR, VDI,
     NIST-JANAF, NIST WebBook, Perry, CRC) for extra liquids and for solids.
     Estimation methods are kept only when nothing else exists and are labelled
     kind = estimated.
  3. The spec v3 values: NIST-JANAF alpha-Al2O3 curve, M(Al2O3), theta_D(Cu) [U].

Run:  python tools/build_database.py      (needs: pip install CoolProp thermo)
"""
import json
import math
import os
import sys

import CoolProp
import CoolProp.CoolProp as CP

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cpcalc.lookup import harvest          # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "cpcalc", "data", "database.json")
P = 101325.0
SKIP = {"R410A", "R404A", "R507A", "R407C", "Air"}          # mixtures / pseudo-pure
ASSOC = {"water", "methanol", "ethanol", "ammonia", "propyleneglycol", "heavywater", "hydrogenchloride"}

EXTRA_LIQUIDS = [
    "1-propanol", "2-propanol", "1-butanol", "2-butanol", "1-pentanol", "1-hexanol", "1-octanol",
    "ethylene glycol", "diethylene glycol", "triethylene glycol", "glycerol", "acetic acid", "formic acid",
    "dimethyl sulfoxide", "N,N-dimethylformamide", "acetonitrile", "chloroform", "carbon tetrachloride",
    "dichloromethane", "pyridine", "aniline", "phenol", "nitrobenzene", "styrene", "cyclohexanol",
    "2-butanone", "ethyl acetate", "methyl acetate", "1,4-dioxane", "benzyl alcohol", "n-hexadecane",
    "ethanolamine", "formamide", "anisole", "oleic acid", "n-tetradecane", "methyl tert-butyl ether",
]
SOLIDS = {  # CAS -> preferred id
    "1344-28-1": "al2o3", "14808-60-7": "sio2", "13463-67-7": "tio2", "1314-13-2": "zno",
    "1317-38-0": "cuo", "1317-39-1": "cu2o", "1309-37-1": "fe2o3", "1317-61-9": "fe3o4",
    "1309-48-4": "mgo", "1314-23-4": "zro2", "1306-38-3": "ceo2", "409-21-2": "sic",
    "7782-42-5": "graphite", "7782-40-3": "diamond", "7440-50-8": "cu", "7440-22-4": "ag",
    "7440-57-5": "au", "7429-90-5": "al", "7439-89-6": "fe", "7440-02-0": "ni", "7440-32-6": "ti",
    "7440-21-3": "si", "24304-00-5": "aln", "10043-11-5": "bn", "471-34-1": "caco3", "7647-14-5": "nacl",
}
SOLID_ALIASES = {"al2o3": ["alumina", "aluminium oxide", "aluminum oxide"], "sio2": ["silica", "quartz"],
                 "tio2": ["titania", "titanium dioxide"], "cu": ["copper"], "ag": ["silver"], "au": ["gold"],
                 "al": ["aluminium", "aluminum"], "fe": ["iron"], "ni": ["nickel"], "ti": ["titanium"],
                 "zno": ["zinc oxide"], "cuo": ["copper(ii) oxide"], "fe3o4": ["magnetite"], "fe2o3": ["hematite"],
                 "mgo": ["magnesia"], "zro2": ["zirconia"], "ceo2": ["ceria"], "sic": ["silicon carbide"],
                 "si": ["silicon"], "aln": ["aluminium nitride"], "bn": ["boron nitride"], "nacl": ["sodium chloride"],
                 "caco3": ["calcium carbonate", "calcite"]}


def grid(lo, hi, n, extra=(298.15,)):
    pts = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    pts += [t for t in extra if lo < t < hi]
    pts += [float(t) for t in range(int(math.ceil(lo / 10.0)) * 10, int(hi), 10)]
    return sorted(set(round(t, 3) for t in pts))


def coolprop_entry(f):
    src = "CoolProp %s reference equation of state for %s (%s)" % (CoolProp.__version__, f, CP.get_BibTeXKey(f, "EOS"))
    rec = lambda key, value, unit: {"key": key, "value": value, "unit": unit, "kind": "experimental", "source": src}
    recs = [rec("M", CP.PropsSI("molar_mass", f), "kg/mol"), rec("Tc", CP.PropsSI("Tcrit", f), "K"),
            rec("Pc", CP.PropsSI("pcrit", f), "Pa"), rec("omega", CP.PropsSI("acentric", f), "-")]
    Tt = max(CP.PropsSI("Ttriple", f), CP.PropsSI("Tmin", f))
    recs.append(rec("T_melt", Tt, "K"))
    try:
        Tb = CP.PropsSI("T", "P", P, "Q", 0, f)
        recs.append(rec("T_boil", Tb, "K"))
    except ValueError:
        Tb = None
    note = "liquid at 101325 Pa, between the triple point and the normal boiling point"
    if Tb and Tb > Tt + 1:
        lo = Tt + 0.001
        cols = {"cp": [], "rho": [], "alpha_V": [], "kappa_T": []}
        for T in grid(lo, Tb - 0.02, 31):
            try:
                cols["cp"].append([T, CP.PropsSI("CPMASS", "T", T, "P", P, f)])
                cols["rho"].append([T, CP.PropsSI("DMASS", "T", T, "P", P, f)])
                cols["alpha_V"].append([T, CP.PropsSI("isobaric_expansion_coefficient", "T", T, "P", P, f)])
                cols["kappa_T"].append([T, CP.PropsSI("isothermal_compressibility", "T", T, "P", P, f)])
            except ValueError:
                for k in cols:
                    cols[k] = [p for p in cols[k] if p[0] != T]
        units = {"cp": "J/kg/K", "rho": "kg/m3", "alpha_V": "1/K", "kappa_T": "1/Pa"}
        n = min(len(v) for v in cols.values())
        if n >= 2:
            for k, pts in cols.items():
                recs.append({"key": k, "state": "liquid", "unit": units[k], "points": pts[:n] if len(pts) == n else pts,
                             "kind": "experimental", "source": src, "note": note})
    Tmax = CP.PropsSI("Tmax", f)
    cp0 = []
    for T in grid(max(Tt, 100.0), min(Tmax, 1500.0), 41, (298.15, 300.0, 400.0)):
        try:
            cp0.append([T, CP.PropsSI("CP0MOLAR", "T", T, "P", 1000.0, f)])
        except ValueError:
            pass
    if len(cp0) >= 2:
        recs.append({"key": "cp_ig", "state": "gas", "unit": "J/mol/K", "points": cp0, "kind": "experimental",
                     "source": src, "note": "ideal-gas part of the equation of state"})
    aliases = [a.strip().lower() for a in CP.get_fluid_param_string(f, "aliases").split(",") if a.strip()]
    formula = CP.get_fluid_param_string(f, "formula").replace("_{", "").replace("}", "").replace("1", "") \
        if "_{" in CP.get_fluid_param_string(f, "formula") else ""
    return {"name": f, "cas": CP.get_fluid_param_string(f, "CAS"), "formula": formula, "aliases": aliases,
            "associating": f.lower() in ASSOC, "origin": "CoolProp %s" % CoolProp.__version__, "records": recs}


def main():
    db = {}
    cas_seen = set()
    for f in CP.get_global_param_string("FluidsList").split(","):
        if f in SKIP:
            continue
        try:
            e = coolprop_entry(f)
        except Exception as exc:
            print("skip", f, exc)
            continue
        db[f.lower()] = e
        cas_seen.add(e["cas"])
    print("CoolProp fluids:", len(db))
    for name in EXTRA_LIQUIDS:
        try:
            e = harvest(name, include=("liquid", "gas"))
        except LookupError as exc:
            print("skip", name, exc)
            continue
        if e["cas"] in cas_seen:
            continue
        cas_seen.add(e["cas"])
        db[name.lower()] = e
    for cas, cid in SOLIDS.items():
        try:
            e = harvest(cas, include=("solid",))
        except LookupError as exc:
            print("skip", cas, exc)
            continue
        e["aliases"] = sorted(set(e["aliases"] + SOLID_ALIASES.get(cid, []) + [cas, e["name"].lower()]))
        e["name"] = {"al2o3": "Al2O3 (alpha-alumina)", "sio2": "SiO2 (quartz)", "tio2": "TiO2"}.get(cid, e["name"])
        db[cid] = e
    # spec v3 values
    spec = json.load(open(os.path.join(os.path.dirname(__file__), "spec_v1_database.json")))["components"]
    al = db["al2o3"]
    al["records"] = [r for r in al["records"] if not (r["key"] == "cp" and r.get("state") == "solid")]
    c = spec["al2o3"]["curves"][0]
    al["records"].append({"key": "cp", "state": "solid", "unit": c["unit"], "points": c["points"],
                          "kind": "experimental", "source": c["source"]})
    for r in spec["cu"]["properties"]:
        db["cu"]["records"].append({"key": r["key"], "state": "solid", "value": r["value"], "unit": r["unit"],
                                    "kind": r["kind"], "source": r["source"]})
    # room-temperature expansivity and compressibility of common particle materials (needed for c_v of suspensions)
    TE = "Wikipedia 'Thermal expansion' table, volumetric coefficient at 20 C (from CRC Handbook data)"
    KD = "KnowledgeDoor Elements Handbook, isothermal bulk modulus at 300 K; kappa_T = 1/K"
    NIST = "NIST SRD 30 Property Data Summaries, sintered alpha-alumina (>= 99.5 %%), 20 C: %s"
    solid_ak = {
        "al2o3": (3 * 4.6e-6, NIST % "linear expansion 4.6e-6 1/K, alpha_V = 3 alpha_L", 1 / 257e9, NIST % "bulk modulus 257 GPa"),
        "cu": (51e-6, TE, 1 / 137e9, KD + " (137 GPa)"), "ag": (54e-6, TE, 1 / 100.7e9, KD + " (100.7 GPa)"),
        "au": (42e-6, TE, 1 / 173.2e9, KD + " (173.2 GPa)"), "al": (69e-6, TE, 1 / 72.2e9, KD + " (72.2 GPa)"),
        "fe": (33.3e-6, TE, 1 / 168.3e9, KD + " (168.3 GPa)"), "ni": (39e-6, TE, 1 / 186e9, KD + " (186 GPa)"),
        "si": (9e-6, TE, 1 / 98.8e9, KD + " (98.8 GPa)"),
    }
    for cid, (a, sa, k, sk) in solid_ak.items():
        for key, v, src, unit in (("alpha_V", a, sa, "1/K"), ("kappa_T", k, sk, "1/Pa")):
            db[cid]["records"].append({"key": key, "state": "solid", "value": v, "unit": unit, "T_min": 250.0,
                                       "T_max": 350.0, "kind": "experimental", "source": src,
                                       "note": "room-temperature handbook value, used from 250 to 350 K"})
    # tidy: drop records with no points/values, sort by name
    for e in db.values():
        e["records"] = [r for r in e["records"] if ("points" in r and len(r["points"]) >= 2) or "value" in r]
    out = {"_about": "cpcalc V2 database: built by tools/build_database.py from CoolProp %s reference equations, "
                     "thermo %s / chemicals data methods (each record names its source) and spec v3 values. "
                     "Liquid curves are at 101325 Pa. kind: experimental = measured or evaluated data, "
                     "derived = computed from such data, estimated = estimation method, unspecified = unverified."
                     % (CoolProp.__version__, __import__("thermo").__version__),
           "components": dict(sorted(db.items()))}
    with open(OUT, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("components:", len(db), "file size: %.0f kB" % (os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()

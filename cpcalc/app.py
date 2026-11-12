"""cpcalc web interface (Streamlit). Start it with:   python -m cpcalc ui
(or: streamlit run cpcalc/app.py). The interface only edits a case dictionary
and calls the engine; all thermodynamics lives in the engine."""
import copy
import hashlib
import io
import json
import os
import sys
import tempfile

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cpcalc import database, examples, report, theory, workbook            # noqa: E402
from cpcalc import mixtures as mx                                              # noqa: E402
from cpcalc.constants import (STATES, ROLES, PURE_METHODS, MIX_MODELS, MIX_BASES, KINDS, PROPS, NEEDED,
                              PAIR_KEYS, ERRORS, WARNINGS)                     # noqa: E402
from cpcalc.engine import run_case, run_sweep                                 # noqa: E402
from cpcalc.errors import CalcError                                           # noqa: E402
from cpcalc.properties import preview, canon, range_text                      # noqa: E402
from cpcalc.units import allowed_units                                        # noqa: E402

st.set_page_config(page_title="cpcalc - apparent cp and cv", page_icon=":thermometer:", layout="wide")
st.markdown("""<style>
.block-container{padding-top:3.2rem;max-width:1250px}
div[data-testid="stMetricValue"]{font-size:1.6rem}
.small{color:#6b7280;font-size:.85rem}
.step-title{font-weight:600;margin-top:.2rem}.step-ref{color:#6b7280;font-weight:400;float:right;font-size:.85rem}
</style>""", unsafe_allow_html=True)

ss = st.session_state
METHOD_CHOICES = ["auto"] + ["data", "Peng-Robinson", "ideal gas", "Debye"]
SWEEP_LABELS = {"none": "no sweep", "T": "temperature", "phi": "amount of one phase", "x": "composition of a mixture"}
PROP_LABEL = {k: "%s - %s" % (k, v[3]) for k, v in PROPS.items()}


# ================================================================== state
def load(case):
    case = copy.deepcopy(case)
    case.setdefault("mixtures", {})
    for key in ("data", "curves", "pairs", "phases"):
        case.setdefault(key, [])
    base = database.with_extra(database.load_database(), ss.get("extra", {}))
    mixes = [m.lower() for m in case["mixtures"]]
    for p in case["phases"]:
        if str(p.get("substance", "")).lower() not in mixes:
            p["substance"] = canon(base, p["substance"])
    for m in case["mixtures"].values():
        m["components"] = {canon(base, c_): x for c_, x in m["components"].items()}
    for rows, keys in ((case["data"], ["component"]), (case["curves"], ["component"]), (case["pairs"], ["i", "j"])):
        for r in rows:
            for k in keys:
                r[k] = canon(base, r.get(k, ""))
    ss.case = case
    ss.v = ss.get("v", 0) + 1                          # new editor widgets after a load


def md(text):
    """Write c_p, c_v, c_p,app ... as inline LaTeX in Markdown."""
    import re
    text = re.sub(r"\bc_([pv]),app\b", r"$c_{\1,\\mathrm{app}}$", text)
    return re.sub(r"\bc_([pv])\b", r"$c_\1$", text)


if "case" not in ss:
    ss.extra = {}
    ss.custom = []
    start = "D3 Al2O3 in water, 2 vol% (spec Fig. 1 values)"
    want_ex = st.query_params.get("example", "")            # e.g. ?example=D6 opens that example
    for name in examples.EXAMPLES:
        if want_ex and name.lower().startswith(want_ex.lower()):
            start = name
            break
    load(examples.get(start))
case = ss.case
db = database.with_extra(database.load_database(), ss.extra)


def compound_options():
    names = set(database.choices(db)) | set(ss.custom)
    for p in case["phases"]:
        if p.get("substance") and str(p["substance"]).lower() not in [m.lower() for m in case["mixtures"]]:
            names.add(canon(db, p["substance"]))
    for m in case["mixtures"].values():
        names |= {canon(db, c) for c in m["components"]}
    return sorted(names)


def digest(df):
    return hashlib.md5(df.to_json().encode()).hexdigest()[:10]


def clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def xlsx_bytes(case_, db_):
    """The case as an .xlsx workbook (bytes) for the download buttons."""
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        workbook.save_case(case_, path, db_)
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.remove(path)


def load_xlsx(data):
    """Read an uploaded .xlsx workbook into a case dictionary."""
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        return workbook.load_case(path)
    finally:
        os.remove(path)


# ================================================================== sidebar
with st.sidebar:
    st.markdown("## cpcalc")
    st.caption("Apparent c_p and c_v of fluids, mixtures, suspensions and emulsions. V3")
    pick = st.selectbox("Start from an example", list(examples.EXAMPLES), index=2)
    if st.button("Load example", width="stretch"):
        load(examples.get(pick))
        st.rerun()
    with st.container(border=True):
        st.markdown("**Save / open a case (Excel)**")
        st.caption("A *case* is everything you set in tabs 1 and 2: temperature, pressure, phases, mixtures, "
                   "your own values and pair parameters. Save it to continue later or to share it; open it here to restore it.")
        up = st.file_uploader("Open a saved case (.xlsx)", type=["xlsx"],
                              help="A workbook saved by this tool (or made from the blank template below).")
        if up is not None and st.button("Load this case", width="stretch"):
            try:
                load(load_xlsx(up.getvalue()))
                st.rerun()
            except CalcError as err:
                for p in err.problems:
                    st.error(p["what"])
        st.download_button("Download this case (.xlsx)", xlsx_bytes(case, db), file_name="cpcalc_case.xlsx", width="stretch",
                           help="Everything currently in tabs 1 and 2, as an Excel workbook you can edit and open again.")
        if "template_xlsx" not in ss:
            ss.template_xlsx = xlsx_bytes(examples.get("Blank"), database.load_database())
        st.download_button("Download a blank template (.xlsx)", ss.template_xlsx, file_name="cpcalc_blank_case.xlsx", width="stretch",
                           help="An empty workbook with the six sheets (Setup, Phases, Mixtures, Data, Curves, Pairs) and drop-down lists.")

    st.divider()
    with st.container(border=True):
        st.markdown("**➕ Add a compound**")
        st.caption("Compound not in the drop-down lists? Add it here, then pick it in the Phases or Mixtures tables.")
        q = st.text_input("Name, formula or CAS number", placeholder="e.g. 1-butanol, 75-65-0, toluene")
        c1, c2 = st.columns(2)
        if c1.button("Find in thermo", width="stretch", disabled=not q,
                     help="Looks the compound up in the open thermo/chemicals data bank and adds its data with sources"):
            try:
                from cpcalc.lookup import harvest
                with st.spinner("Searching the data bank..."):
                    entry = harvest(q)
                cid = q.strip().lower()
                ss.extra[cid] = entry
                st.success("Added '%s' (%s) with %d data records." % (entry["name"], entry["cas"], len(entry["records"])))
            except LookupError as err:
                st.error(str(err))
        if c2.button("Add as my own", width="stretch", disabled=not q,
                     help="Adds the name to the lists; then type its data in the Data tab"):
            ss.custom.append(q.strip().lower())
            st.success("'%s' added. Give its data in tab 2." % q.strip().lower())
        st.caption("%d compounds in the database. Any other compound: add it above." % len(db["components"]))
    with st.expander("Browse the database"):
        s = st.text_input("Search", key="dbsearch")
        rows = [{"id": cid, "name": e.get("name"), "CAS": e.get("cas"), "source": e.get("origin")}
                for cid, e in db["components"].items()]
        df = pd.DataFrame(rows)
        if s:
            df = df[df.apply(lambda r: s.lower() in " ".join(str(x).lower() for x in r.values), axis=1)]
        st.dataframe(df, hide_index=True, height=260)


# ================================================================== tabs
t1, t2, t3, t4, t5 = st.tabs(["1  System", "2  Data", "3  Results", "4  Calculation sheet", "5  Theory"])

# ------------------------------------------------------------------ 1. system
with t1:
    c = st.columns([2.2, 1, 0.7, 1, 0.7, 1.4, 1.6])
    case["name"] = c[0].text_input("Case name", case.get("name", "my case"))
    tunit = c[2].selectbox("T unit", ["K", "°C"], key="tunit")
    Tshow = case["T"] - 273.15 if tunit == "°C" else case["T"]
    Tin = c[1].number_input("Temperature", value=float(round(Tshow, 4)), step=1.0, format="%.2f")
    case["T"] = Tin + 273.15 if tunit == "°C" else Tin
    punit = c[4].selectbox("P unit", ["bar", "atm", "kPa", "Pa"], key="punit")
    pf = {"bar": 1e5, "atm": 101325.0, "kPa": 1e3, "Pa": 1.0}[punit]
    case["P"] = c[3].number_input("Pressure", value=float(case["P"] / pf), format="%.5g") * pf
    case["quantity"] = c[5].radio("Calculate", ["both", "cp", "cv"], horizontal=True,
                                  index=["both", "cp", "cv"].index(case.get("quantity", "both")))
    case["basis"] = c[6].radio("Phase amounts are", ["volume", "mass"], horizontal=True,
                               format_func=lambda b: b + " fractions", index=["volume", "mass"].index(case.get("basis", "volume")))

    st.markdown("#### Phases")
    st.markdown("<span class='small'>One row per phase. <b>substance</b> is a compound from the list or the name of a "
                "mixture defined below. <b>method</b> = auto tries data first (gases: Peng-Robinson first).</span>",
                unsafe_allow_html=True)
    mix_names = list(case["mixtures"])
    opts = compound_options() + mix_names
    if "phases0" not in ss or ss.get("phases_v") != ss.v:
        ss.phases0 = pd.DataFrame(case["phases"], columns=["name", "state", "substance", "amount", "role", "method"])
        ss.phases0["amount"] = ss.phases0["amount"].astype("float64")
        ss.phases_v = ss.v
    ph_df = st.data_editor(
        ss.phases0, key="phases_%d" % ss.v, num_rows="dynamic", width="stretch", hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("phase name", required=True),
            "state": st.column_config.SelectboxColumn("state", options=STATES, required=True),
            "substance": st.column_config.SelectboxColumn("substance (compound or mixture)", options=opts, required=True, width="medium"),
            "amount": st.column_config.NumberColumn("amount (fraction)", min_value=0.0, max_value=1.0, format="%.5f", required=True),
            "role": st.column_config.SelectboxColumn("role", options=ROLES),
            "method": st.column_config.SelectboxColumn("method", options=METHOD_CHOICES)})
    case["phases"] = [{k: clean(v) for k, v in r.items()} for r in ph_df.to_dict("records") if clean(r.get("substance"))]
    for p in case["phases"]:
        p["method"] = p.get("method") or "auto"
    total = sum(float(p["amount"] or 0) for p in case["phases"])
    (st.caption if abs(total - 1) < 1e-3 else st.warning)("Sum of the amounts: %.5f (must be 1)" % total)
    st.caption("Compound missing from the lists? Use **➕ Add a compound** in the sidebar on the left "
               "(on a phone, open the sidebar with the arrow at the top left).")

    st.markdown("#### Mixtures")
    st.markdown("<span class='small'>A mixture is one phase made of several compounds. Give its components and "
                "fractions; pick the basis (mole, mass or volume of the pure components) and the model.</span>",
                unsafe_allow_html=True)
    for name in list(case["mixtures"]):
        m = case["mixtures"][name]
        with st.expander("Mixture: %s   (%d components, %s fractions, model %s)" % (name, len(m["components"]), m.get("basis"), m.get("model")),
                         expanded=True):
            a, b, d = st.columns([1, 1, 1])
            m["basis"] = a.selectbox("fractions are", MIX_BASES, index=MIX_BASES.index(m.get("basis", "mole")), key="mb_%s_%d" % (name, ss.v))
            m["model"] = b.selectbox("model", MIX_MODELS, index=MIX_MODELS.index(m.get("model", "auto")), key="mm_%s_%d" % (name, ss.v),
                                     help="auto: NRTL or Margules if their pair parameters are given, else ideal; "
                                          "gases: Peng-Robinson if T_c, P_c, omega are known, else ideal gas")
            if d.button("Remove this mixture", key="mx_rm_%s_%d" % (name, ss.v)):
                del case["mixtures"][name]
                ss.v += 1
                st.rerun()
            k0 = "mix0_%s" % name
            if k0 not in ss or ss.get(k0 + "_v") != ss.v:
                ss[k0] = pd.DataFrame([{"component": canon(db, c_), "fraction": x} for c_, x in m["components"].items()],
                                      columns=["component", "fraction"])
                ss[k0]["fraction"] = ss[k0]["fraction"].astype("float64")
                ss[k0 + "_v"] = ss.v
            mdf = st.data_editor(ss[k0], key="mix_%s_%d" % (name, ss.v), num_rows="dynamic", hide_index=True, width="stretch",
                                 column_config={"component": st.column_config.SelectboxColumn("component", options=compound_options(), required=True),
                                                "fraction": st.column_config.NumberColumn("fraction", min_value=0.0, max_value=1.0, format="%.5f")})
            m["components"] = {r["component"]: float(clean(r["fraction"]) or 0) for r in mdf.to_dict("records") if clean(r.get("component"))}
            st.caption("sum of fractions: %.5f" % sum(m["components"].values()))
    a, b = st.columns([2, 1])
    newmix = a.text_input("New mixture name", placeholder="e.g. coolant", label_visibility="collapsed")
    if b.button("Add mixture", disabled=not newmix):
        case["mixtures"][newmix] = {"basis": "mass", "model": "auto", "components": {"water": 1.0}}
        ss.v += 1
        st.rerun()


    # ---- Advanced: type the model parameters yourself (writes into the pair-parameter table below)
    def pair_val(key, i, j, symmetric=False):
        for p_ in case["pairs"]:
            if p_["key"] == key and ((p_["i"] == i and p_["j"] == j) or (symmetric and p_["i"] == j and p_["j"] == i)):
                return float(p_["value"])
        return None

    nrtl_slot = nrtl_pair = None
    with st.expander("Advanced: type the model parameters yourself (NRTL, Margules, k_ij)"):
        st.markdown("<span class='small'>Use this when your own source (a textbook, a paper, an assignment) gives the parameters. "
                    "Fill the boxes and press <b>Apply</b>: the values go into the pair-parameter table below, which you can "
                    "still edit. Values for a single compound (molar mass, density, c_p, T_c, ...) are typed in tab 2 <b>Data</b>, "
                    "column <b>your value</b>; they always win over the database.</span>", unsafe_allow_html=True)
        mix_list = list(case["mixtures"])
        if not mix_list:
            st.info("Add a mixture first (the box above), then come back here.")
        else:
            a_, b_ = st.columns(2)
            mname = a_.selectbox("Mixture", mix_list, key="adv_mix_%d" % ss.v,
                                 index=mix_list.index(ss.get("adv_sel")) if ss.get("adv_sel") in mix_list else 0)
            ss.adv_sel = mname
            mixture = case["mixtures"][mname]
            adv_models = ["NRTL", "Margules", "Peng-Robinson k_ij"]
            first = {"Margules": 1, "Peng-Robinson": 2, "ideal gas": 2}.get(mixture.get("model"), 0)
            model = b_.radio("Parameters for", adv_models, index=first, horizontal=True, key="adv_model_%s_%d" % (mname, ss.v))
            comps = [canon(db, c_) for c_ in mixture["components"]]
            fk = "%s_%d" % (mname, ss.v)
            if model != "Peng-Robinson k_ij" and len(comps) != 2:
                st.info("%s is for a mixture of exactly two components (this one has %d). Use the Peng-Robinson k_ij option, "
                        "or change the components in the mixture table above." % (model, len(comps)))
            elif model == "NRTL":
                c1_, c2_ = comps
                with st.form("adv_nrtl_" + fk):
                    st.markdown("tau_ij = a_ij + b_ij / T + e_ij ln T   (T in K), G_ij = exp(-alpha tau_ij). "
                                "**If your source gives tau = A / T, type A in the b box and leave a and e at 0.**")
                    alpha = st.number_input("alpha (non-randomness parameter)", format="%.4g", step=0.05,
                                            value=pair_val("nrtl_alpha", c1_, c2_, True) if pair_val("nrtl_alpha", c1_, c2_, True) is not None else 0.30)
                    vals = {}
                    for tag, i_, j_ in (("12", c1_, c2_), ("21", c2_, c1_)):
                        cols = st.columns([1.3, 1, 1, 1])
                        cols[0].markdown("**tau_%s**  (%s -> %s)" % (tag, i_, j_))
                        for col, k_, lab in zip(cols[1:], ("a", "b", "e"), ("a_%s" % tag, "b_%s  (K)" % tag, "e_%s" % tag)):
                            cur = pair_val("nrtl_" + k_, i_, j_)
                            vals[(i_, j_, k_)] = col.number_input(lab, value=cur if cur is not None else 0.0, format="%.6g", step=0.1,
                                                                   key="adv_n_%s_%s_%s" % (k_, tag, fk))
                    k1, k2 = st.columns([1, 2])
                    kind = k1.selectbox("kind of data", KINDS, index=KINDS.index("experimental"), key="adv_nk_" + fk)
                    src = k2.text_input("source (optional)", key="adv_ns_" + fk, placeholder="e.g. Arce et al. 1997")
                    go = st.form_submit_button("Apply to the pair-parameter table")
                if go:
                    drop = {"nrtl_a", "nrtl_b", "nrtl_e", "nrtl_alpha"}
                    case["pairs"] = [p_ for p_ in case["pairs"] if not (p_["key"] in drop and {p_["i"], p_["j"]} == {c1_, c2_})]
                    def add(i_, j_, key_, v_):
                        case["pairs"].append({"i": i_, "j": j_, "key": key_, "value": float(v_), "kind": kind,
                                              "source": src or "typed in the Advanced section"})
                    add(c1_, c2_, "nrtl_alpha", alpha)
                    for i_, j_ in ((c1_, c2_), (c2_, c1_)):
                        given = [(k_, vals[(i_, j_, k_)]) for k_ in ("a", "b", "e") if vals[(i_, j_, k_)] != 0]
                        for k_, v_ in (given or [("b", 0.0)]):
                            add(i_, j_, "nrtl_" + k_, v_)
                    mixture["model"] = "NRTL"
                    ss.v += 1
                    st.rerun()
                nrtl_slot, nrtl_pair = st.empty(), (c1_, c2_)        # filled after the pair table, so it is never one edit behind
            elif model == "Margules":
                c1_, c2_ = comps
                with st.form("adv_marg_" + fk):
                    st.markdown("G^E / RT = x_1 x_2 (A + B / T + D ln T)   (T in K). With B = D = 0 it is the one-parameter Margules form.")
                    cols = st.columns(3)
                    mv = {}
                    for col, k_, lab in zip(cols, ("A", "B", "D"), ("A", "B  (K)", "D")):
                        cur = pair_val("marg_" + k_, c1_, c2_, True)
                        mv[k_] = col.number_input(lab, value=cur if cur is not None else 0.0, format="%.6g", step=0.1, key="adv_m_%s_%s" % (k_, fk))
                    k1, k2 = st.columns([1, 2])
                    kind = k1.selectbox("kind of data", KINDS, index=KINDS.index("experimental"), key="adv_mk_" + fk)
                    src = k2.text_input("source (optional)", key="adv_ms_" + fk, placeholder="e.g. fitted to H^E data of ...")
                    go = st.form_submit_button("Apply to the pair-parameter table")
                if go:
                    drop = {"marg_A", "marg_B", "marg_D"}
                    case["pairs"] = [p_ for p_ in case["pairs"] if not (p_["key"] in drop and {p_["i"], p_["j"]} == {c1_, c2_})]
                    for k_ in ("A", "B", "D"):
                        if mv[k_] != 0 or k_ == "D":               # D is always written: the model needs it
                            case["pairs"].append({"i": c1_, "j": c2_, "key": "marg_" + k_, "value": float(mv[k_]), "kind": kind,
                                                  "source": src or "typed in the Advanced section"})
                    mixture["model"] = "Margules"
                    ss.v += 1
                    st.rerun()
            else:
                pairs_ = [(comps[a], comps[b]) for a in range(len(comps)) for b in range(a + 1, len(comps))]
                if not pairs_:
                    st.info("A mixture needs at least two components for k_ij.")
                else:
                    with st.form("adv_kij_" + fk):
                        st.markdown("Binary interaction parameter k_ij of the Peng-Robinson mixing rule (gas mixtures). "
                                    "Typical values are small (0 to 0.1); 0 means no interaction correction.")
                        kv = {}
                        cols = st.columns(min(3, len(pairs_)))
                        for n_, (i_, j_) in enumerate(pairs_):
                            cur = pair_val("kij", i_, j_, True)
                            kv[(i_, j_)] = cols[n_ % len(cols)].number_input("k_ij  (%s, %s)" % (i_, j_), value=cur if cur is not None else 0.0,
                                                                              format="%.5g", step=0.01, key="adv_k_%d_%s" % (n_, fk))
                        k1, k2 = st.columns([1, 2])
                        kind = k1.selectbox("kind of data", KINDS, index=KINDS.index("experimental"), key="adv_kk_" + fk)
                        src = k2.text_input("source (optional)", key="adv_ks_" + fk)
                        go = st.form_submit_button("Apply to the pair-parameter table")
                    if go:
                        case["pairs"] = [p_ for p_ in case["pairs"] if not (p_["key"] == "kij" and (p_["i"], p_["j"]) in
                                                                          set(pairs_) | {(j_, i_) for i_, j_ in pairs_})]
                        for (i_, j_), v_ in kv.items():
                            case["pairs"].append({"i": i_, "j": j_, "key": "kij", "value": float(v_), "kind": kind,
                                                  "source": src or "typed in the Advanced section"})
                        ss.v += 1
                        st.rerun()

    if case["mixtures"] or case["pairs"]:
        with st.expander("All pair parameters (table view: NRTL, Margules, k_ij)", expanded=bool(case["pairs"])):
            st.markdown("<span class='small'>NRTL: tau_ij = nrtl_a + nrtl_b/T + nrtl_e ln T for the ordered pair i -> j, "
                        "plus nrtl_alpha. Margules: marg_A, marg_B, marg_D. Peng-Robinson: kij (blank = 0).</span>",
                        unsafe_allow_html=True)
            if "pairs0" not in ss or ss.get("pairs_v") != ss.v:
                ss.pairs0 = pd.DataFrame(case["pairs"], columns=["i", "j", "key", "value", "kind", "source"])
                ss.pairs0["value"] = ss.pairs0["value"].astype("float64")
                ss.pairs_v = ss.v
            pdf = st.data_editor(ss.pairs0, key="pairs_%d" % ss.v, num_rows="dynamic", hide_index=True, width="stretch",
                                 column_config={"i": st.column_config.SelectboxColumn("component i", options=compound_options()),
                                                "j": st.column_config.SelectboxColumn("component j", options=compound_options()),
                                                "key": st.column_config.SelectboxColumn("parameter", options=PAIR_KEYS),
                                                "value": st.column_config.NumberColumn("value", format="%.6g"),
                                                "kind": st.column_config.SelectboxColumn("kind", options=KINDS),
                                                "source": st.column_config.TextColumn("source", width="large")})
            case["pairs"] = [{k: clean(v) for k, v in r.items()} for r in pdf.to_dict("records") if clean(r.get("key"))]
    if nrtl_slot is not None:
        c1_, c2_ = nrtl_pair
        a_ok = pair_val("nrtl_alpha", c1_, c2_, True)
        if a_ok is not None:
            par = {"alpha": a_ok}
            for tag, i_, j_ in (("12", c1_, c2_), ("21", c2_, c1_)):
                for k_ in ("a", "b", "e"):
                    par[k_ + tag] = pair_val("nrtl_" + k_, i_, j_) or 0.0
            sm = mx.nrtl_summary(par, case["T"])
            nrtl_slot.caption("With the table values at T = %.2f K:  tau_12 = %.5g,  tau_21 = %.5g,  G_12 = %.5g,  G_21 = %.5g.  "
                              "At infinite dilution the activity coefficients are  gamma_%s = %.4g  and  gamma_%s = %.4g."
                              % (case["T"], sm["tau12"], sm["tau21"], sm["G12"], sm["G21"], c1_, sm["gamma1_inf"], c2_, sm["gamma2_inf"]))

    st.markdown("#### Sweep (optional)")
    sw = case.get("sweep") or {}
    a, b, c_, d, e = st.columns([1.4, 1.4, 1, 1, 0.8])
    var = a.selectbox("Vary", list(SWEEP_LABELS), format_func=SWEEP_LABELS.get,
                      index=list(SWEEP_LABELS).index(sw.get("variable", "none")) if sw else 0)
    if var == "none":
        case.pop("sweep", None)
    else:
        targets = [p["name"] for p in case["phases"]] if var == "phi" else (list(case["mixtures"]) if var == "x" else [""])
        tgt = b.selectbox("of", targets or [""], index=targets.index(sw["target"]) if sw.get("target") in targets else 0,
                          disabled=var == "T")
        lo_d, hi_d = (case["T"] - 20, case["T"] + 40) if var == "T" else (0.0, 0.1 if var == "phi" else 1.0)
        same = sw.get("variable") == var
        start = c_.number_input("from" + (" (K)" if var == "T" else ""), value=float(sw["start"]) if same else float(lo_d), format="%.4g")
        stop = d.number_input("to" + (" (K)" if var == "T" else ""), value=float(sw["stop"]) if same else float(hi_d), format="%.4g")
        n = e.number_input("points", value=int(sw.get("n", 11)) if same else 11, min_value=2, max_value=101)
        case["sweep"] = {"variable": var, "start": start, "stop": stop, "n": int(n), "target": tgt}


# ------------------------------------------------------------------ 2. data
def needed_rows():
    rows, seen = [], set()
    mixes = {k.lower(): v for k, v in case["mixtures"].items()}
    for p in case["phases"]:
        sub = str(p.get("substance") or "")
        state = p.get("state") or "liquid"
        comps = [canon(db, c_) for c_ in mixes[sub.lower()]["components"]] if sub.lower() in mixes else [canon(db, sub)]
        keys = NEEDED[state]
        if sub.lower() not in mixes and p.get("method") == "Debye":
            keys = keys + ["theta_D", "n_atoms", "gamma_e"]
        for comp in comps:
            for k in keys:
                if (comp, k, state) not in seen and comp:
                    seen.add((comp, k, state))
                    rows.append((comp, k, state))
    return rows


with t2:
    st.markdown("For each compound and property, the value used at **T = %.2f K**. Blank *your value* means the "
                "database value is used; anything you type always wins. Nothing is extrapolated." % case["T"])
    try:
        probe = {k: case[k] for k in ("T", "P")}
        probe.update({"data": [], "curves": [], "pairs": []})
        user = {"data": [dict(d_, component=canon(db, d_["component"]), state=(d_.get("state") or "").lower())
                         for d_ in case["data"] if clean(d_.get("value")) is not None and d_.get("key") in PROPS],
                "curves": [dict(c_, component=canon(db, c_["component"])) for c_ in case["curves"]], "T": case["T"], "P": case["P"]}
        table = []
        for comp, key, state in needed_rows():
            rec_db, tried = preview(probe, db, comp, key, state)
            rec_all, tried_all = preview(user, db, comp, key, state)
            mine = [d_ for d_ in user["data"] if d_["component"] == comp and d_["key"] == key and d_["state"] in ("", state)]
            mine = mine[0] if mine else {}
            if rec_all is None:
                status = "missing" + (" (data cover %s)" % tried_all[0].split("valid ")[-1] if tried_all and "valid" in tried_all[0] else "")
            else:
                status = {"yours": "your value", "your curve": "your curve", "derived": "derived"}.get(rec_all["route"], "database")
            table.append({"compound": comp, "state": state, "property": key,
                          "in use (SI)": ("%.6g %s" % (rec_all["value"], rec_all["unit"])) if rec_all else "",
                          "status": ("✅ " if rec_all else "❌ ") + status,
                          "database (SI)": ("%.6g" % rec_db["value"]) if rec_db else "",
                          "your value": clean(mine.get("value")), "unit": mine.get("unit") or PROPS[key][2],
                          "valid from K": clean(mine.get("T_min")), "valid to K": clean(mine.get("T_max")),
                          "kind": mine.get("kind") or "unspecified", "source": mine.get("source") or "",
                          "database source": rec_db["source"] if rec_db else ""})
        base = pd.DataFrame(table)
        for col in ("your value", "valid from K", "valid to K"):
            if col in base:
                base[col] = pd.to_numeric(base[col], errors="coerce").astype("float64")
        if not base.empty:            # editable columns first, database columns last
            base = base[["compound", "state", "property", "status", "in use (SI)", "your value", "unit", "valid from K",
                         "valid to K", "kind", "source", "database (SI)", "database source"]]
        if base.empty:
            st.info("Add phases in tab 1 first.")
        else:
            units = sorted({u for k in PROPS for u in allowed_units(k)})
            edited = st.data_editor(
                base, key="check_%s_%d" % (digest(base), ss.v), hide_index=True, width="stretch", height=min(640, 38 + 35 * len(base)),
                disabled=["compound", "state", "property", "in use (SI)", "status", "database (SI)", "database source"],
                column_config={"your value": st.column_config.NumberColumn("your value", format="%.6g"),
                               "unit": st.column_config.SelectboxColumn("unit", options=units),
                               "kind": st.column_config.SelectboxColumn("kind", options=KINDS),
                               "status": st.column_config.TextColumn("status", width="medium"),
                               "source": st.column_config.TextColumn("your source", width="medium"),
                               "database source": st.column_config.TextColumn("database source", width="large")})
            if not edited.equals(base):
                shown = {(r["compound"], r["property"]) for r in table}
                keep = [d_ for d_ in case["data"] if (canon(db, d_["component"]), d_["key"]) not in shown]
                for r in edited.to_dict("records"):
                    if clean(r["your value"]) is not None:
                        keep.append({"component": r["compound"], "key": r["property"], "value": float(r["your value"]),
                                     "unit": r["unit"], "state": r["state"], "T_min": clean(r["valid from K"]),
                                     "T_max": clean(r["valid to K"]), "kind": r["kind"] or "unspecified",
                                     "source": r["source"] or "typed in the interface"})
                case["data"] = keep
                st.rerun()
    except CalcError as err:
        st.error("; ".join(p["what"] for p in err.problems))

    with st.expander("Temperature curves: your (T, value) points", expanded=bool(case["curves"])):
        st.markdown("<span class='small'>One row per point; at least two points per compound and property. "
                    "Values are interpolated linearly and never extrapolated. A density curve also gives alpha_V.</span>",
                    unsafe_allow_html=True)
        if "curves0" not in ss or ss.get("curves_v") != ss.v:
            pts = [{"component": cu["component"], "property": cu["key"], "state": cu.get("state", ""), "T": T, "value": y,
                    "unit": cu.get("unit"), "kind": cu.get("kind"), "source": cu.get("source")}
                   for cu in case["curves"] for T, y in cu["points"]]
            ss.curves0 = pd.DataFrame(pts, columns=["component", "property", "state", "T", "value", "unit", "kind", "source"])
            ss.curves0[["T", "value"]] = ss.curves0[["T", "value"]].astype("float64")
            ss.curves_v = ss.v
        cdf = st.data_editor(ss.curves0, key="curves_%d" % ss.v, num_rows="dynamic", hide_index=True, width="stretch",
                             column_config={"component": st.column_config.SelectboxColumn("component", options=compound_options()),
                                            "property": st.column_config.SelectboxColumn("property", options=list(PROPS)),
                                            "state": st.column_config.SelectboxColumn("state", options=STATES),
                                            "T": st.column_config.NumberColumn("T (K)", format="%.2f"),
                                            "value": st.column_config.NumberColumn("value", format="%.6g"),
                                            "unit": st.column_config.SelectboxColumn("unit", options=sorted({u for k in PROPS for u in allowed_units(k)})),
                                            "kind": st.column_config.SelectboxColumn("kind", options=KINDS)})
        curves = {}
        for r in cdf.to_dict("records"):
            if clean(r.get("component")) and clean(r.get("property")) and clean(r.get("T")) is not None and clean(r.get("value")) is not None:
                k = (r["component"], r["property"], r.get("state") or "")
                cu = curves.setdefault(k, {"component": k[0], "key": k[1], "state": k[2], "unit": r.get("unit") or PROPS[k[1]][2],
                                           "kind": r.get("kind") or "unspecified", "source": r.get("source") or "", "points": []})
                cu["points"].append([float(r["T"]), float(r["value"])])
        case["curves"] = list(curves.values())


# ------------------------------------------------------------------ calculation (always current)
def calculate():
    try:
        res = run_case(case, db)
        swp = run_sweep(case, db) if case.get("sweep") else None
        return res, swp, None
    except CalcError as err:
        return None, None, err.problems


res, swp, input_errors = calculate()


def show_problems(problems):
    for p in problems:
        with st.container(border=True):
            st.markdown(":red[**%s - %s**]  %s" % (p["code"], ERRORS.get(p["code"], ""), p["what"]))
            if p.get("lines"):
                st.markdown("\n".join("- " + l for l in p["lines"]))
            if p.get("fix"):
                st.caption(p["fix"])


# ------------------------------------------------------------------ 3. results
with t3:
    if input_errors:
        st.error("The case cannot be run until these inputs are fixed:")
        show_problems(input_errors)
    elif res:
        badge = {"calculated": "green", "calculated under assumptions": "orange", "partly calculable": "orange",
                 "not calculable": "red"}[res["status"]]
        st.markdown("### %s  \n:%s-badge[**%s**]%s" % (res["name"], badge, res["status"].upper(),
                                                   "  (illustrative inputs)" if res["illustrative"] else ""))
        m = st.columns(4)
        cpv = res["results"].get("cp_app", {}).get("value")
        cvv = res["results"].get("cv_app", {}).get("value")
        if "cp_app" in res["results"]:
            m[0].metric(r"$c_{p,\mathrm{app}}$  [J/kg/K]", "%.2f" % cpv if cpv is not None else "not calculable")
        if "cv_app" in res["results"]:
            m[1].metric(r"$c_{v,\mathrm{app}}$  [J/kg/K]", "%.2f" % cvv if cvv is not None else "not calculable")
        if cpv is not None and cvv is not None:
            m[2].metric(r"$c_p - c_v$  [J/kg/K]", "%.3f" % (cpv - cvv))
        if res["molar"]:
            m[3].metric(r"molar $C_p$, $C_v$  [J/mol/K]", "  ".join("%s %.3f" % (k, v) for k, v in res["molar"].items()))
        if res["problems"]:
            st.markdown("#### What is missing")
            show_problems(res["problems"])
        flags = ["**%s** %s" % (w["code"], w["text"]) for w in res["warnings"]]
        flags += ["**assumed** %s (%s)" % (a["text"], a["detail"]) for a in res["assumptions"]["used"]]
        if flags:
            st.warning("\n".join("- " + x for x in flags))
        for n_ in res["notes"]:
            st.info(n_)
        st.markdown("#### Phases")
        rows = [{"phase": p["name"], "substance": p["substance"], "state": p["state"], "phi": p.get("phi"), "w": p.get("w"),
                 "c_p [J/kg/K]": p.get("cp"), "c_v [J/kg/K]": p.get("cv"), "rho [kg/m3]": p.get("rho"),
                 "method c_p / c_v": "%s / %s" % (p.get("method_cp") or "-", p.get("method_cv") or "-")} for p in res["phases"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={k: st.column_config.NumberColumn(format="%.5f" if k in ("phi", "w") else "%.2f")
                                    for k in ("phi", "w", "c_p [J/kg/K]", "c_v [J/kg/K]", "rho [kg/m3]")})
        d = res["diagnostics"]
        if "volume_weighted" in d or "sum_w_cv" in d:
            txt = []
            if "volume_weighted" in d:
                txt.append("Volume-weighted (Pak-Cho) form: %.2f J/kg/K (%+.1f %% vs the mass-weighted result; diagnostic only)."
                           % (d["volume_weighted"], d["volume_weighted_pct"]))
            if "sum_w_cv" in d:
                txt.append("Naive mass average of the phase c_v: %.2f J/kg/K; the true c_v,app is higher by %.3f (Eq. 23 gives %.3f)."
                           % (d["sum_w_cv"], d["gap"], d["gap_eq23"]))
            st.caption(" ".join(txt))
        if res["checks"]:
            st.caption("Checks: " + " | ".join(("OK " if c_["ok"] else "FAILED ") + c_["name"] for c_ in res["checks"]))

        if swp:
            st.markdown("#### Sweep")
            xl = {"T": "T [K]", "phi": "phi of %s" % swp["target"], "x": "x1 in %s" % swp["target"]}[swp["variable"]]
            pts = []
            for p in swp["points"]:
                r = p["result"]
                pts.append({xl: p["x"], "c_p,app": r["results"].get("cp_app", {}).get("value") if r else None,
                            "c_v,app": r["results"].get("cv_app", {}).get("value") if r else None,
                            "status": r["status"] if r else "error " + p["error"][0]["code"]})
            sdf = pd.DataFrame(pts)
            ycols = [c_ for c_ in ("c_p,app", "c_v,app") if sdf[c_].notna().any()]
            if ycols:
                import altair as alt
                long = sdf.rename(columns={xl: "x"}).melt(id_vars=["x"], value_vars=ycols, var_name="quantity",
                                                          value_name="y").dropna()
                chart = alt.Chart(long).mark_line(point=True).encode(
                    x=alt.X("x:Q", title=xl, scale=alt.Scale(zero=False)),
                    y=alt.Y("y:Q", title="J/kg/K", scale=alt.Scale(zero=False)), color=alt.Color("quantity:N", title=None),
                    tooltip=[alt.Tooltip("x:Q", title=xl), "quantity", alt.Tooltip("y:Q", title="J/kg/K", format=".2f")]
                ).properties(height=340)
                st.altair_chart(chart, width="stretch")
            st.dataframe(sdf, hide_index=True, width="stretch")
            st.download_button("Download sweep (CSV)", sdf.to_csv(index=False), file_name="sweep.csv")

        with st.expander("Where every input came from (provenance)"):
            st.dataframe(pd.DataFrame([{"compound": p["comp"], "property": p["key"], "value (SI)": p["value"], "unit": p["unit"],
                                        "kind": p["kind"], "route": p["route"], "source": p["source"]} for p in res["provenance"]]),
                         hide_index=True, width="stretch")
        a, b, c_ = st.columns(3)
        a.download_button("Calculation sheet (HTML)", report.html_sheet(res), file_name="calculation_sheet.html", width="stretch")
        b.download_button("Text report", report.text_report(res, explain=True), file_name="report.txt", width="stretch")
        c_.download_button("Result (JSON)", report.to_json(res), file_name="result.json", width="stretch")


# ------------------------------------------------------------------ 4. calculation sheet
with t4:
    if not res:
        st.info("No result yet: fix the inputs listed in tab 3.")
    else:
        st.markdown("### Route taken")
        for ph, items in res["routes"].items():
            lines = []
            for it in items:
                tried = ["~~%s~~ (missing: %s)" % (t["method"], ", ".join(t["lacks"])) for t in it["tried"]]
                chosen = (":green[**%s**] (%s)" % (it["chosen"], it["how"])) if it["chosen"] else ":red[**no method complete**]"
                lines.append("- **%s**, %s: %s" % (ph, md(it["quantity"]), "  ->  ".join(tried + [chosen])))
            st.markdown("\n".join(lines))
        st.markdown("### Step by step")
        for i, s in enumerate(res["steps"], 1):
            with st.container(border=True):
                a_, b_ = st.columns([5, 1])
                a_.markdown("**Step %d** &nbsp; %s" % (i, md(s["title"])))
                b_.caption(s["ref"])
                for tag in ("eq", "sub", "res"):
                    if s[tag]:
                        st.latex(s[tag])
                if s["info"]:
                    st.caption(s["info"])
        st.download_button("Download this sheet as HTML", report.html_sheet(res), file_name="calculation_sheet.html")


# ------------------------------------------------------------------ 5. theory
with t5:
    left, right = st.columns([1, 3])
    titles = [t["title"] for t in theory.TOPICS]
    pick_t = left.radio("Topic", titles, label_visibility="collapsed")
    topic = theory.TOPICS[titles.index(pick_t)]
    with right:
        st.markdown("### " + topic["title"])
        st.markdown(md(topic["text"]))
        if topic.get("diagram"):
            st.graphviz_chart(topic["diagram"])
        for eq, cap in topic["equations"]:
            st.latex(eq)
            st.caption(cap)
        if topic.get("gives"):
            st.markdown(md("**In and out.** " + topic["gives"]))
        if topic.get("holds"):
            st.info("**Holds when:** " + topic["holds"])
        if topic.get("where"):
            st.success("**Where in the app:** " + topic["where"])
        if topic.get("next"):
            st.markdown("**Next:** " + topic["next"])
        st.caption("In the code: " + topic["code"])

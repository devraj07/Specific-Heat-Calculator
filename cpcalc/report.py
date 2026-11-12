"""Reports: plain text (terminal), an HTML calculation sheet (LaTeX via KaTeX) and JSON.
Interface layer: returns strings, never prints."""
import html
import json
import textwrap
from datetime import datetime

from .constants import ERRORS
from .latex import to_text

W = 78


def f(x, d=2):
    if x is None:
        return "-"
    if x != 0 and (abs(x) < 1e-3 or abs(x) >= 1e6):
        return "%.4e" % x
    return "%.*f" % (d, x)


def wrap(prefix, text, indent=None):
    return textwrap.fill(text, W, initial_indent=prefix, subsequent_indent=indent or " " * len(prefix))


def table(headers, rows, right):
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(str(c).rjust(widths[i]) if right[i] else str(c).ljust(widths[i])
                                   for i, c in enumerate(cells)).rstrip()
    return [line(headers), "  ".join("-" * w for w in widths)] + [line(r) for r in rows]


def phase_rows(res):
    rows = []
    for p in res["phases"]:
        short = {"c_p-c_v identity": "identity", "Peng-Robinson": "PR"}
        m = "%s/%s" % (short.get(p.get("method_cp"), p.get("method_cp") or "-"), short.get(p.get("method_cv"), p.get("method_cv") or "-"))
        rows.append([p["name"][:12], p["substance"][:12], f(p.get("phi"), 4), f(p.get("w"), 4), f(p.get("cp")),
                     f(p.get("cv")), m[:18]])
    return rows


def problems_text(problems):
    out = []
    for p in problems:
        out.append(wrap("ERROR %s (%s): " % (p["code"], ERRORS.get(p["code"], "")), p["what"], "    "))
        for l in p.get("lines", []):
            out.append(wrap("    ", l, "      "))
        if p.get("fix"):
            out.append(wrap("    fix: ", p["fix"], "      "))
    return "\n".join(out)


def text_report(res, explain=False):
    L = ["CASE %s" % res["name"],
         "T = %.2f K   P = %.0f Pa   amounts: %s fractions" % (res["T"], res["P"], res["basis"]),
         "STATUS %s%s" % (res["status"].upper(), " (illustrative inputs)" if res["illustrative"] else ""), ""]
    L += table(["phase", "substance", "phi", "w", "cp J/kg/K", "cv J/kg/K", "method cp/cv"], phase_rows(res),
               [0, 0, 1, 1, 1, 1, 0])
    L.append("")
    r = res["results"]
    parts = ["%s = %s" % (k, (f(v["value"]) + " J/kg/K") if v["value"] is not None else "not calculable") for k, v in r.items()]
    L.append("RESULT  " + "   ".join(parts))
    if res["molar"]:
        L.append("MOLAR   " + "   ".join("%s = %s J/mol/K" % (k, f(v, 3)) for k, v in res["molar"].items()))
    d = res["diagnostics"]
    if "volume_weighted" in d:
        L.append(wrap("DIAG    ", "volume-weighted (Pak-Cho) %s J/kg/K (%+.1f %% vs mass-weighted)" % (
            f(d["volume_weighted"]), d["volume_weighted_pct"])))
    if "sum_w_cv" in d:
        L.append(wrap("        ", "sum w c_v,k = %s J/kg/K, gap %s (Eq. 23: %s)" % (f(d["sum_w_cv"]), f(d["gap"], 3), f(d["gap_eq23"], 3))))
    if res["checks"]:
        L.append(wrap("CHECKS  ", " | ".join("%s %s" % (c["name"], "ok" if c["ok"] else "FAILED") for c in res["checks"])))
    for w_ in res["warnings"]:
        L.append(wrap("WARNING ", "%s %s" % (w_["code"], w_["text"])))
    for a in res["assumptions"]["used"]:
        L.append(wrap("ASSUMED ", "%s (%s)" % (a["text"], a["detail"])))
    for n in res["notes"]:
        L.append(wrap("NOTE    ", n))
    if res["problems"]:
        L += ["", problems_text(res["problems"])]
    if explain:
        L += ["", "CALCULATION SHEET"]
        for i, s in enumerate(res["steps"], 1):
            L.append(wrap("[%d] " % i, s["title"] + ("  (%s)" % s["ref"] if s["ref"] else "")))
            for tag in ("eq", "sub", "res"):
                if s[tag]:
                    L.append(wrap("     ", to_text(s[tag]), "       "))
            if s["info"]:
                L.append(wrap("     note: ", s["info"], "       "))
    return "\n".join(L)


def sweep_text(sw):
    label = {"T": "T [K]", "phi": "phi(%s)" % sw["target"], "x": "x1 in %s" % sw["target"]}[sw["variable"]]
    rows = []
    for p in sw["points"]:
        r = p["result"]
        if r is None:
            rows.append([f(p["x"], 4), "-", "-", "error " + p["error"][0]["code"]])
        else:
            rows.append([f(p["x"], 4), f(r["results"].get("cp_app", {}).get("value")),
                         f(r["results"].get("cv_app", {}).get("value")), r["status"]])
    return "\n".join(table([label, "cp_app J/kg/K", "cv_app J/kg/K", "status"], rows, [1, 1, 1, 0]))


def html_sheet(res, sweep=None):
    """Self-contained HTML calculation sheet; equations rendered by KaTeX (needs internet for the fonts/script)."""
    e = html.escape
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(p["name"]), e(p["substance"]), f(p.get("phi"), 4), f(p.get("w"), 4), f(p.get("cp")), f(p.get("cv")),
        e("%s / %s" % (p.get("method_cp") or "-", p.get("method_cv") or "-"))) for p in res["phases"])
    results = "".join("<div class='res'><b>%s</b> = %s</div>" % (
        k.replace("_app", ",app"), (f(v["value"]) + " J kg<sup>-1</sup> K<sup>-1</sup>") if v["value"] is not None else
        "not calculable") for k, v in res["results"].items())
    routes = ""
    for ph, items in res["routes"].items():
        for it in items:
            tried = "".join("<li class='no'>%s &mdash; missing: %s</li>" % (e(t["method"]), e(", ".join(t["lacks"]))) for t in it["tried"])
            ok = "<li class='ok'>%s (%s)</li>" % (e(it["chosen"]), e(it["how"])) if it["chosen"] else "<li class='no'>no method complete</li>"
            routes += "<p><b>%s</b>, %s:</p><ul>%s%s</ul>" % (e(ph), e(it["quantity"]), tried, ok)
    steps = ""
    for i, s in enumerate(res["steps"], 1):
        steps += "<div class='step'><div class='st'>Step %d &nbsp; %s <span class='ref'>%s</span></div>" % (i, e(s["title"]), e(s["ref"]))
        for tag in ("eq", "sub", "res"):
            if s[tag]:
                steps += "<div class='%s'>$$%s$$</div>" % (tag, s[tag])
        if s["info"]:
            steps += "<div class='info'>%s</div>" % e(s["info"])
        steps += "</div>"
    probs = "".join("<div class='err'><b>%s</b> %s<ul>%s</ul><i>%s</i></div>" % (
        p["code"], e(p["what"]), "".join("<li>%s</li>" % e(l) for l in p["lines"]), e(p["fix"])) for p in res["problems"])
    warns = "".join("<li>%s %s</li>" % (w_["code"], e(w_["text"])) for w_ in res["warnings"])
    warns += "".join("<li>assumed: %s (%s)</li>" % (e(a["text"]), e(a["detail"])) for a in res["assumptions"]["used"])
    prov = "".join("<tr><td>%s</td><td>%s</td><td>%.6g %s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(p["comp"]), e(p["key"]), p["value"], e(p["unit"]), e(p["kind"]), e(p["route"]), e(p["source"])) for p in res["provenance"])
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Calculation sheet - %(name)s</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true}]});"></script>
<style>body{font-family:Georgia,serif;max-width:900px;margin:2em auto;color:#222;line-height:1.45}
h1{font-size:1.5em;margin-bottom:0}h2{font-size:1.15em;border-bottom:1px solid #ccc;margin-top:1.6em}
table{border-collapse:collapse;font-size:.9em}td,th{border-bottom:1px solid #ddd;padding:3px 8px;text-align:left}
.step{margin:1em 0;padding-left:.8em;border-left:3px solid #8aa}.st{font-weight:bold}.ref{color:#777;font-weight:normal;float:right}
.res{font-size:1.1em}.info{color:#555;font-size:.9em}.err{background:#fff3f3;padding:.5em;margin:.5em 0}
li.ok{color:#176217}li.no{color:#8a1c1c}.status{font-variant:small-caps;font-size:1.1em}</style></head><body>
<h1>Calculation sheet: %(name)s</h1><p>T = %(T).2f K, P = %(P).0f Pa, phase amounts as %(basis)s fractions.
Generated %(time)s by cpcalc %(ver)s.</p><p class="status">Status: %(status)s</p>%(results)s
<h2>Phases</h2><table><tr><th>phase</th><th>substance</th><th>&phi;</th><th>w</th><th>c<sub>p</sub></th><th>c<sub>v</sub></th><th>method</th></tr>%(rows)s</table>
<h2>Route taken</h2>%(routes)s<h2>Step by step</h2>%(steps)s
%(probs_h)s%(probs)s<h2>Warnings and assumptions</h2><ul>%(warns)s</ul>
<h2>Where every input came from</h2><table><tr><th>compound</th><th>property</th><th>value (SI)</th><th>kind</th><th>route</th><th>source</th></tr>%(prov)s</table>
</body></html>""" % {"name": e(res["name"]), "T": res["T"], "P": res["P"], "basis": res["basis"],
                     "time": datetime.now().strftime("%Y-%m-%d %H:%M"), "ver": res["version"], "status": res["status"],
                     "results": results, "rows": rows, "routes": routes, "steps": steps,
                     "probs_h": "<h2>What is missing</h2>" if probs else "", "probs": probs, "warns": warns, "prov": prov}


def to_json(res):
    return json.dumps(dict(res, timestamp=datetime.now().isoformat(timespec="seconds")), indent=1, default=str)

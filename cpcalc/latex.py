"""Small helpers to write numbers and units in LaTeX, and to turn LaTeX into
plain text for the terminal."""
import re

UNIT = {
    "J/kg/K": r"\mathrm{J\,kg^{-1}\,K^{-1}}", "J/mol/K": r"\mathrm{J\,mol^{-1}\,K^{-1}}",
    "kg/m3": r"\mathrm{kg\,m^{-3}}", "1/K": r"\mathrm{K^{-1}}", "1/Pa": r"\mathrm{Pa^{-1}}",
    "K": r"\mathrm{K}", "Pa": r"\mathrm{Pa}", "kg/mol": r"\mathrm{kg\,mol^{-1}}", "J/mol": r"\mathrm{J\,mol^{-1}}",
    "m3/mol": r"\mathrm{m^3\,mol^{-1}}", "-": "",
}


def num(x, sig=6):
    """A number for LaTeX: plain for 1e-3 <= |x| < 1e5, else a x 10^b."""
    if x is None:
        return r"\text{--}"
    if x == 0:
        return "0"
    if 1e-3 <= abs(x) < 1e5:
        return "%.*g" % (sig, x)
    m, e = ("%.4e" % x).split("e")
    return r"%s\times10^{%d}" % (m.rstrip("0").rstrip("."), int(e))


def q(x, unit, sig=6):
    """Number with unit."""
    u = UNIT.get(unit, r"\mathrm{%s}" % unit)
    return num(x, sig) + (r"\ " + u if u else "")


_SYMBOLS = {r"\alpha": "alpha", r"\kappa": "kappa", r"\rho": "rho", r"\phi": "phi", r"\theta": "theta",
            r"\gamma": "gamma", r"\omega": "omega", r"\tau": "tau", r"\Delta": "Delta", r"\sigma": "sigma",
            r"\sum": "sum", r"\ln": "ln", r"\times": "x", r"\cdot": "*", r"\geq": ">=", r"\leq": "<=",
            r"\approx": "~", r"\quad": "  ", r"\qquad": "    ", r"\infty": "inf", r"\int": "int", r"\to": "->",
            r"\left": "", r"\right": "", r"\Rightarrow": "=>", r"\neq": "!=", r"\partial": "d", r"\mathrm": "",
            r"\text": "", r"\displaystyle": "", r"\;": " ", r"\,": " ", r"\!": "", r"\ ": " "}


def to_text(s):
    """Rough plain-text version of a LaTeX string (for the terminal)."""
    if not s:
        return ""
    prev = None
    while prev != s:                                    # innermost \frac and \sqrt first
        prev = s
        s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
        s = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", s)
        s = re.sub(r"\\(?:mathrm|text|operatorname)\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\^\{([^{}]*)\}", r"^\1", s)
        s = re.sub(r"_\{([^{}]*)\}", r"_\1", s)
    for k in sorted(_SYMBOLS, key=len, reverse=True):
        s = s.replace(k, " " + _SYMBOLS[k] + " " if _SYMBOLS[k].isalpha() else _SYMBOLS[k])
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r" ([_^)])", r"\1", s)
    s = re.sub(r"\( ", "(", s)
    return s.strip()

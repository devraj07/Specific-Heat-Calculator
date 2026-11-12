"""Unit conversion: the only place where units are converted."""
from .constants import UNITS, PROPS
from .errors import CalcError, problem


def clean_unit(unit):
    u = "" if unit is None else str(unit).strip()
    u = u.replace(" ", "").replace("^", "").replace("³", "3").replace("°", "")
    if u.lower() in ("degc", "c"):
        return "C"
    if u.lower() == "k":
        return "K"
    return u


def allowed_units(key):
    return [u for u in UNITS[PROPS[key][1]] if u]


def needs_M(key, unit):
    return UNITS[PROPS[key][1]].get(clean_unit(unit)) in ("molar", "specific")


def to_si(key, value, unit, M=None):
    """Convert value given in 'unit' to the SI unit of property 'key'."""
    unit = clean_unit(unit)
    table = UNITS[PROPS[key][1]]
    if unit not in table:
        raise CalcError(problem("E02", "unit '%s' is not allowed for %s" % (unit, key),
                                "use one of: " + ", ".join(allowed_units(key))))
    f = table[unit]
    if f == "celsius":
        return float(value) + 273.15
    if f == "molar":                      # J/mol/K -> J/kg/K
        if not M:
            raise CalcError(problem("E02", "%s per mole needs the molar mass M" % key, "give M or use J/kg/K"))
        return float(value) / M
    if f == "specific":                   # J/kg/K -> J/mol/K
        if not M:
            raise CalcError(problem("E02", "%s per kg needs the molar mass M" % key, "give M or use J/mol/K"))
        return float(value) * UNITS["specific_heat"][unit] * M
    return float(value) * f


def temperature_K(value, unit="K"):
    return to_si("Tc", value, unit)


def pressure_Pa(value, unit="Pa"):
    return to_si("Pc", value, unit)

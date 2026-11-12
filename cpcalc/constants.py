"""Fixed data used everywhere: constants, property list, units, methods, messages.
No calculations here."""

R = 8.314462618          # gas constant, J/mol/K (exact SI value)
P_ATM = 101325.0

# Evidence kinds, strongest first. A result is only as strong as its weakest input.
KINDS = ["experimental", "derived", "unspecified", "estimated", "illustrative"]

# key: (LaTeX symbol, dimension, SI unit, description)
PROPS = {
    "M":       (r"M",          "molar_mass",      "kg/mol",   "molar mass"),
    "cp":      (r"c_p",        "specific_heat",   "J/kg/K",   "heat capacity at constant pressure"),
    "cp_ig":   (r"C_p^{ig}",   "molar_heat",      "J/mol/K",  "ideal-gas heat capacity"),
    "rho":     (r"\rho",       "density",         "kg/m3",    "density"),
    "alpha_V": (r"\alpha_V",   "expansivity",     "1/K",      "volume expansivity"),
    "kappa_T": (r"\kappa_T",   "compressibility", "1/Pa",     "isothermal compressibility"),
    "Tc":      (r"T_c",        "temperature",     "K",        "critical temperature"),
    "Pc":      (r"P_c",        "pressure",        "Pa",       "critical pressure"),
    "omega":   (r"\omega",     "dimensionless",   "-",        "acentric factor"),
    "theta_D": (r"\theta_D",   "temperature",     "K",        "Debye temperature"),
    "n_atoms": (r"n",          "dimensionless",   "-",        "atoms per formula unit"),
    "gamma_e": (r"\gamma_e",   "electronic",      "J/mol/K2", "electronic heat-capacity coefficient"),
    "T_melt":  (r"T_m",        "temperature",     "K",        "melting point"),
    "T_boil":  (r"T_b",        "temperature",     "K",        "normal boiling point"),
}
CONSTANT_KEYS = ["M", "Tc", "Pc", "omega", "theta_D", "n_atoms", "gamma_e", "T_melt", "T_boil"]

# Properties shown in the data-check table for each physical state
NEEDED = {
    "liquid": ["cp", "rho", "alpha_V", "kappa_T", "M"],
    "solid":  ["cp", "rho", "alpha_V", "kappa_T", "M"],
    "gas":    ["cp_ig", "M", "Tc", "Pc", "omega"],
}

# Allowed units per dimension: unit -> factor to SI ("molar"/"specific"/"celsius" are special)
UNITS = {
    "specific_heat":   {"J/kg/K": 1.0, "kJ/kg/K": 1000.0, "J/g/K": 1000.0, "J/mol/K": "molar"},
    "molar_heat":      {"J/mol/K": 1.0, "J/kg/K": "specific", "kJ/kg/K": "specific"},
    "density":         {"kg/m3": 1.0, "g/cm3": 1000.0},
    "expansivity":     {"1/K": 1.0},
    "compressibility": {"1/Pa": 1.0, "1/bar": 1.0e-5, "1/GPa": 1.0e-9},
    "molar_mass":      {"kg/mol": 1.0, "g/mol": 1.0e-3},
    "pressure":        {"Pa": 1.0, "kPa": 1.0e3, "bar": 1.0e5, "atm": 101325.0, "MPa": 1.0e6},
    "temperature":     {"K": 1.0, "C": "celsius"},
    "dimensionless":   {"-": 1.0, "": 1.0},
    "electronic":      {"J/mol/K2": 1.0},
}

STATES = ["liquid", "solid", "gas"]
ROLES = ["continuous", "dispersed"]

# Methods a user can pick for a pure phase ("auto" tries them in this order)
PURE_METHODS = {
    "liquid": ["data", "Peng-Robinson"],
    "solid":  ["data", "Debye"],
    "gas":    ["Peng-Robinson", "ideal gas", "data"],
}
AUTO_PURE = {"liquid": ["data"], "solid": ["data", "Debye"], "gas": ["Peng-Robinson", "ideal gas", "data"]}

# Mixture models ("auto": NRTL or Margules if parameters are given, else ideal; gases: Peng-Robinson, else ideal gas)
MIX_MODELS = ["auto", "ideal", "NRTL", "Margules", "Peng-Robinson", "ideal gas"]
MIX_BASES = ["mole", "mass", "volume"]
PAIR_KEYS = ["kij", "marg_A", "marg_B", "marg_D", "nrtl_a", "nrtl_b", "nrtl_e", "nrtl_alpha"]

# Assumptions the engine may make; each is reported and lowers the status
ASSUMPTIONS = {
    "ce_zero": "excess heat capacity C_p^E = 0 (ideal mixture)",
    "ve_zero": "excess volume V^E = 0 (mixture density, alpha_V, kappa_T and c_v)",
    "kij_zero": "binary parameter k_ij = 0 where not given",
    "gamma_e_zero": "electronic term gamma_e T = 0 (exact for non-metals)",
    "no_T_range": "a value without a temperature range is used as T-independent",
}

STANDING_ASSUMPTIONS = [
    "one temperature and one pressure for all phases (slow heating)",
    "frozen phases: no melting, boiling, dissolution or reaction",
    "interface and particle-size effects neglected",
    "liquid data from the database are at 1 atm; the pressure effect on condensed phases is neglected",
]

ERRORS = {
    "E01": "missing data", "E02": "input or unit error", "E03": "fraction error",
    "E04": "outside the data range", "E05": "no equation-of-state root", "E06": "model scope",
    "E07": "physical limit", "E09": "not supported", "E10": "broken reference",
}

WARNINGS = {
    "A02": "fractions renormalised", "A03": "dispersed fraction above phi_warn", "A04": "near-critical state",
    "A05": "metastable EOS root", "A06": "EOS used for an associating fluid", "A07": "mixture stability not checked",
    "A08": "illustrative data in use", "A09": "your value differs from the database by > 5 %",
    "A10": "excess volume neglected", "A11": "Peng-Robinson used for a liquid", "A12": "PR78 m(omega) branch",
    "A13": "supercritical: liquid/vapour request overridden",
}

WHERE_TO_LOOK = {
    "cp": "NIST WebBook, NIST-JANAF (solids), DIPPR/Perry or CRC (liquids)",
    "cp_ig": "NIST WebBook (Shomate), Poling-Prausnitz-O'Connell appendix",
    "rho": "CRC Handbook, DIPPR, supplier data sheet",
    "alpha_V": "CRC Handbook; or give rho at two or more temperatures (a rho curve)",
    "kappa_T": "CRC Handbook; for solids kappa_T = 1/(bulk modulus)",
    "M": "the formula",
    "Tc": "NIST WebBook, Poling-Prausnitz-O'Connell appendix",
    "Pc": "NIST WebBook, Poling-Prausnitz-O'Connell appendix",
    "omega": "Poling-Prausnitz-O'Connell appendix",
    "theta_D": "Kittel, CRC Handbook",
    "n_atoms": "the formula",
}

DEFAULTS = {"name": "my case", "T": 298.15, "P": P_ATM, "quantity": "both", "basis": "volume", "phi_warn": 0.60}

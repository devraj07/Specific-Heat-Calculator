"""cpcalc V3 - apparent c_p and c_v of pure fluids, mixtures and multiphase samples.

    from cpcalc import run_case, run_sweep
    result = run_case(case_dict)
"""
from .engine import run_case, run_sweep, VERSION
from .errors import CalcError

__version__ = VERSION

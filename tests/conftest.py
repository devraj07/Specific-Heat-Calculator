import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def two_phase(phi=0.02, basis="volume", quantity="both", T=298.15, kind="experimental"):
    """Synthetic liquid 'fluid' + solid 'part' (neither is in the database)."""
    def v(c, k, val, unit, state):
        return {"component": c, "key": k, "value": val, "unit": unit, "state": state, "kind": kind, "source": "test",
                "T_min": 200.0, "T_max": 400.0}
    return {"name": "test", "T": T, "P": 101325.0, "quantity": quantity, "basis": basis,
            "phases": [{"name": "L", "state": "liquid", "substance": "fluid", "amount": 1 - phi, "role": "continuous"},
                       {"name": "S", "state": "solid", "substance": "part", "amount": phi, "role": "dispersed"}],
            "data": [v("fluid", "cp", 4000.0, "J/kg/K", "liquid"), v("fluid", "rho", 1000.0, "kg/m3", "liquid"),
                     v("fluid", "alpha_V", 2.0e-4, "1/K", "liquid"), v("fluid", "kappa_T", 5.0e-10, "1/Pa", "liquid"),
                     v("part", "cp", 800.0, "J/kg/K", "solid"), v("part", "rho", 4000.0, "kg/m3", "solid"),
                     v("part", "alpha_V", 2.0e-5, "1/K", "solid"), v("part", "kappa_T", 4.0e-12, "1/Pa", "solid")]}

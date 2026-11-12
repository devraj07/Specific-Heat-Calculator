"""Pure-phase equations: Peng-Robinson (spec Sec. 3.3), the c_p - c_v identity
and the Debye model (Sec. 3.4).

All quantities are molar SI: J/mol/K, m3/mol, Pa. One function per equation.
"""
import math

import numpy as np
from scipy.integrate import quad

from .errors import CalcError, problem
from .constants import R

SQ2 = math.sqrt(2.0)
ZC_PR = 0.3074                 # PR critical compressibility (spec P3)


def pr_m(omega):
    """Eq. 7: m(omega); PR78 branch above omega = 0.491."""
    if omega <= 0.491:
        return 0.37464 + 1.54226 * omega - 0.26992 * omega ** 2
    return 0.379642 + 1.48503 * omega - 0.164423 * omega ** 2 + 0.016666 * omega ** 3


def pr_parameters(Tc, Pc, omega, T, m=None):
    """Eqs. 6-8: a(T), a'(T), a''(T) and b for one component."""
    ac = 0.45724 * R ** 2 * Tc ** 2 / Pc
    b = 0.07780 * R * Tc / Pc
    if m is None:
        m = pr_m(omega)
    s = math.sqrt(T / Tc)
    a = ac * (1.0 + m * (1.0 - s)) ** 2
    da = -ac * m * (1.0 + m * (1.0 - s)) / math.sqrt(T * Tc)
    d2a = ac * m * (1.0 + m) / (2.0 * T * math.sqrt(T * Tc))
    return {"a": a, "da": da, "d2a": d2a, "b": b, "ac": ac, "m": m}


def pr_pressure(T, v, a, b):
    """Eq. 6."""
    return R * T / (v - b) - a / (v * v + 2.0 * b * v - b * b)


def pr_roots(T, P, a, b):
    """Eq. 10: real roots of the cubic in Z with Z > B (rule P1), sorted."""
    A = a * P / (R * T) ** 2
    B = b * P / (R * T)
    coeffs = [1.0, -(1.0 - B), A - 3.0 * B ** 2 - 2.0 * B, -(A * B - B ** 2 - B ** 3)]
    all_roots = np.roots(coeffs)
    real = sorted(float(z.real) for z in all_roots if abs(z.imag) < 1e-9 * max(1.0, abs(z.real)))
    kept = [z for z in real if z > B]
    return kept, real, A, B


def ln_phi(Z, A, B):
    """Eq. 11: fugacity coefficient (used only for phase selection)."""
    return (Z - 1.0 - math.log(Z - B)
            - A / (2.0 * SQ2 * B) * math.log((Z + (1.0 + SQ2) * B) / (Z + (1.0 - SQ2) * B)))


def dP_dT_v(T, v, b, da):
    """Eq. 9, (dP/dT)_v."""
    return R / (v - b) - da / (v * v + 2.0 * b * v - b * b)


def dP_dv_T(T, v, a, b):
    """Eq. 9, (dP/dv)_T."""
    return -R * T / (v - b) ** 2 + 2.0 * a * (v + b) / (v * v + 2.0 * b * v - b * b) ** 2


def cv_residual(T, v, b, d2a):
    """Eq. 9: closed-form C_v^R = T a''/(2 sqrt2 b) ln[(v+(1+sqrt2)b)/(v+(1-sqrt2)b)]."""
    return T * d2a / (2.0 * SQ2 * b) * math.log((v + (1.0 + SQ2) * b) / (v + (1.0 - SQ2) * b))


def h_residual_over_RT(T, Z, A, B, a, da, b):
    """H^R/RT = (Z-1) + (T a' - a)/(2 sqrt2 b R T) ln[(Z+(1+sqrt2)B)/(Z+(1-sqrt2)B)] (TC-05)."""
    return (Z - 1.0) + (T * da - a) / (2.0 * SQ2 * b * R * T) * math.log(
        (Z + (1.0 + SQ2) * B) / (Z + (1.0 - SQ2) * B))


def select_root(roots, A, B, request, T, P, b, Tc=None, Pc=None, sat_tol=1e-6):
    """Phase selection P1-P4. Returns dict with Z, label and flags.
    request is 'stable', 'liquid' or 'vapour'."""
    warnings = []
    if not roots:
        raise CalcError(problem("E05", "Peng-Robinson has no admissible root (Z > B) at %.2f K, %.0f Pa" % (T, P),
                                "try another method or another T, P"))
    # P4 supercritical
    if Tc is not None and Pc is not None and T > Tc and P > Pc:
        Z = min(roots, key=lambda z: ln_phi(z, A, B))     # lowest ln phi
        if request in ("liquid", "vapour"):
            warnings.append(("A13", "T > Tc and P > Pc: supercritical fluid; '%s' request overridden" % request))
        return {"Z": Z, "label": "supercritical fluid", "warnings": warnings, "metastable": False}
    if len(roots) >= 2:                  # P2 (middle root never used)
        ZL, ZV = roots[0], roots[-1]
        lpL, lpV = ln_phi(ZL, A, B), ln_phi(ZV, A, B)
        stable = "liquid" if lpL < lpV else "vapour"
        at_sat = abs(lpL - lpV) < sat_tol
        if request == "stable":
            choice = stable
        else:
            choice = request
        Z = ZL if choice == "liquid" else ZV
        metastable = (choice != stable) and not at_sat
        if metastable:
            warnings.append(("A05", "%s root used but the %s root is stable (ln phi %.6f vs %.6f)" % (
                choice, stable, lpL if choice == "liquid" else lpV, lpV if choice == "liquid" else lpL)))
        label = choice + ("-like root, at saturation" if at_sat else "-like root")
        return {"Z": Z, "label": label, "warnings": warnings, "metastable": metastable,
                "lnphi_L": lpL, "lnphi_V": lpV, "stable": stable}
    # P3 one root: heuristic label from reduced density
    Z = roots[0]
    v = Z * R * T / P
    vc = ZC_PR / 0.07780 * b                     # = Zc R Tc / Pc for a pure fluid
    label = "liquid" if vc / v > 1.0 else "vapour"
    if request in ("liquid", "vapour") and request != label:
        raise CalcError(problem("E05", "only one PR root (Z = %.5f, rho/rho_c = %.3f) and it looks %s, "
                                       "but the phase is declared %s" % (Z, vc / v, label, request),
                                "check the phase state, change T or P, or use the data method"))
    return {"Z": Z, "label": label + "-like root (single root, heuristic rho/rho_c)",
            "warnings": warnings, "metastable": False}


def pr_state(T, P, a, b, da, d2a, cp_ig, request="stable", Tc=None, Pc=None, sat_tol=1e-6):
    """Molar C_p, C_v, v, alpha_V, kappa_T from Peng-Robinson (Eqs. 3, 5, 9-11).
    Works for a pure fluid or a mixture (a, b, a', a'' of the mixture)."""
    roots, all_real, A, B = pr_roots(T, P, a, b)
    sel = select_root(roots, A, B, request, T, P, b, Tc, Pc, sat_tol)
    Z = sel["Z"]
    v = Z * R * T / P
    dPdT = dP_dT_v(T, v, b, da)
    dPdv = dP_dv_T(T, v, a, b)
    if dPdv >= 0:
        raise CalcError(problem("E05", "selected root is mechanically unstable ((dP/dv)_T >= 0)"))
    cvr = cv_residual(T, v, b, d2a)
    cp_minus_cv = -T * dPdT ** 2 / dPdv                     # Eq. 3
    cv = cp_ig - R + cvr                                    # Eq. 5
    cp = cv + cp_minus_cv
    alpha = -dPdT / (v * dPdv)
    kappa = -1.0 / (v * dPdv)
    for val in (cp, cv, alpha, kappa):
        if val != val:      # NaN
            raise CalcError(problem("E11", "Peng-Robinson evaluation gave NaN at %.2f K" % T))
    return {"Cp": cp, "Cv": cv, "CvR": cvr, "CpR": cp - cp_ig, "Cp_minus_Cv": cp_minus_cv,
            "Z": Z, "v": v, "A": A, "B": B, "roots": all_real, "admissible_roots": roots,
            "alpha": alpha, "kappa": kappa, "dPdT": dPdT, "dPdv": dPdv,
            "label": sel["label"], "warnings": sel["warnings"], "metastable": sel["metastable"],
            "lnphi_L": sel.get("lnphi_L"), "lnphi_V": sel.get("lnphi_V")}


def saturation_pressure(Tc, Pc, omega, T, P_guess=None):
    """P_sat where ln phi of the outer roots are equal (Table 4 / TC-07).
    Simple bisection on P in log scale; used by tests and validation only."""
    p = pr_parameters(Tc, Pc, omega, T)
    lo, hi = 1.0, Pc

    def diff(P):
        roots, _, A, B = pr_roots(T, P, p["a"], p["b"])
        if len(roots) < 2:
            return None
        return ln_phi(roots[0], A, B) - ln_phi(roots[-1], A, B)

    # find a bracket where both roots exist
    grid = [10 ** (k / 20.0) for k in range(0, int(20 * math.log10(Pc)) + 1)]
    pts = [(P, diff(P)) for P in grid]
    pts = [(P, d) for P, d in pts if d is not None]
    for (P1, d1), (P2, d2) in zip(pts, pts[1:]):
        if d1 * d2 < 0:
            lo, hi = P1, P2
            break
    else:
        raise CalcError(problem("E11", "no saturation bracket found at %.2f K" % T))
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        d = diff(mid)
        if d is None:
            break
        if d * diff(lo) > 0:
            lo = mid
        else:
            hi = mid
        if hi / lo - 1.0 < 1e-12:
            break
    return math.sqrt(lo * hi)


# ------------------------------------------------------------------ condensed phases (Sec. 3.4)
def cp_minus_cv(T, rho, alpha, kappa):
    """Eq. 3, specific form: c_p - c_v = T alpha_V^2 / (rho kappa_T)  [J/kg/K]."""
    return T * alpha ** 2 / (rho * kappa)


def debye_integrand(x):
    """x^4 e^x / (e^x - 1)^2, written so that it never overflows."""
    if x == 0.0:
        return 0.0
    return x ** 4 * math.exp(-x) / (-math.expm1(-x)) ** 2


def debye_cv(T, theta_D, n_atoms, gamma_e=0.0):
    """Eq. 13: C_v = 9 n R (T/theta_D)^3 int_0^{theta_D/T} x^4 e^x/(e^x-1)^2 dx + gamma_e T  [J/mol/K]."""
    integral = quad(debye_integrand, 0.0, theta_D / T, limit=200)[0]
    return 9.0 * n_atoms * R * (T / theta_D) ** 3 * integral + gamma_e * T


def debye_low_T_limit(T, theta_D, n_atoms):
    """T << theta_D: C_v -> (12 pi^4/5) n R (T/theta_D)^3."""
    return 12.0 * math.pi ** 4 / 5.0 * n_atoms * R * (T / theta_D) ** 3

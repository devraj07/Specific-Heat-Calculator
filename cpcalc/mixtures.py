"""Mixtures (spec Sec. 3.5): fraction conversions, ideal mixing, excess functions
(Margules, NRTL) and van der Waals one-fluid mixing for Peng-Robinson."""
import math

from .constants import R

FD_STEP = 0.01      # K, central differences for NRTL


# ------------------------------------------------------------ fractions inside a mixture
def x_to_w(x, M):
    total = sum(x[i] * M[i] for i in x)
    return {i: x[i] * M[i] / total for i in x}


def w_to_x(w, M):
    total = sum(w[i] / M[i] for i in w)
    return {i: (w[i] / M[i]) / total for i in w}


def phi_to_w(phi, rho):
    """Volume fractions of the pure components before mixing -> mass fractions."""
    total = sum(phi[i] * rho[i] for i in phi)
    return {i: phi[i] * rho[i] / total for i in phi}


# ------------------------------------------------------------ excess functions (binary)
def ge_margules(x1, T, A, B, D):
    """Eq. 15: G^E = R T x1 x2 (A + B/T + D ln T)  [J/mol]."""
    return R * T * x1 * (1.0 - x1) * (A + B / T + D * math.log(T))


def margules_he(x1, T, B, D):
    """Eq. 15: H^E = R x1 x2 (B - D T)."""
    return R * x1 * (1.0 - x1) * (B - D * T)


def margules_cpe(x1, T, D):
    """Eq. 15: C_p^E = -R D x1 x2."""
    return -R * D * x1 * (1.0 - x1)


def nrtl_tau(a, b, e, T):
    return a + b / T + e * math.log(T)


def ge_nrtl(x1, T, p):
    """Eq. 16: binary NRTL G^E [J/mol]; p has a12, b12, e12, a21, b21, e21, alpha."""
    x2 = 1.0 - x1
    t12 = nrtl_tau(p["a12"], p["b12"], p["e12"], T)
    t21 = nrtl_tau(p["a21"], p["b21"], p["e21"], T)
    G12, G21 = math.exp(-p["alpha"] * t12), math.exp(-p["alpha"] * t21)
    return R * T * x1 * x2 * (t21 * G21 / (x1 + x2 * G21) + t12 * G12 / (x2 + x1 * G12))


def nrtl_summary(p, T):
    """Numbers shown next to the NRTL inputs: tau, G and the activity coefficients at infinite
    dilution (ln gamma1_inf = tau21 + tau12 G12, ln gamma2_inf = tau12 + tau21 G21).
    p has a12, b12, e12, a21, b21, e21, alpha. Display helper only; the engine does not use it."""
    t12 = nrtl_tau(p["a12"], p["b12"], p["e12"], T)
    t21 = nrtl_tau(p["a21"], p["b21"], p["e21"], T)
    G12, G21 = math.exp(-p["alpha"] * t12), math.exp(-p["alpha"] * t21)
    return {"tau12": t12, "tau21": t21, "G12": G12, "G21": G21,
            "gamma1_inf": math.exp(t21 + t12 * G12), "gamma2_inf": math.exp(t12 + t21 * G21)}


def he_from_ge(ge, T, h=FD_STEP):
    """Eq. 14: H^E = G^E - T dG^E/dT."""
    return ge(T) - T * (ge(T + h) - ge(T - h)) / (2.0 * h)


def cpe_from_ge(ge, T, h=FD_STEP):
    """Eq. 14: C_p^E = -T d2G^E/dT2 (central second difference)."""
    return -T * (ge(T + h) - 2.0 * ge(T) + ge(T - h)) / h ** 2


def partial_molar(func, x1, h=1e-5):
    """B1 = B + x2 dB/dx1, B2 = B - x1 dB/dx1 for a binary property B(x1)."""
    dB = (func(x1 + h) - func(x1 - h)) / (2.0 * h)
    B = func(x1)
    return B + (1.0 - x1) * dB, B - x1 * dB


def gibbs_duhem_residual(func, x1, h=1e-4):
    """x1 dB1/dx1 + x2 dB2/dx1 (should be ~0)."""
    b1p, b2p = partial_molar(func, x1 + h, h)
    b1m, b2m = partial_molar(func, x1 - h, h)
    return x1 * (b1p - b1m) / (2 * h) + (1.0 - x1) * (b2p - b2m) / (2 * h)


# ------------------------------------------------------------ volume properties with V^E = 0
def ideal_volume(w, rho, alpha=None, kappa=None):
    """1/rho = sum w_i/rho_i; alpha = sum phi_i alpha_i; kappa = sum phi_i kappa_i."""
    vol = sum(w[i] / rho[i] for i in w)
    phi = {i: (w[i] / rho[i]) / vol for i in w}
    out = {"rho": 1.0 / vol, "phi": phi, "alpha": None, "kappa": None}
    if alpha and kappa:
        out["alpha"] = sum(phi[i] * alpha[i] for i in w)
        out["kappa"] = sum(phi[i] * kappa[i] for i in w)
    return out


def cp_minus_cv_mixture(T, w, rho, alpha, kappa):
    """Eq. 19 (specific): c_p - c_v = T (sum w_i alpha_i/rho_i)^2 / sum w_i kappa_i/rho_i."""
    num = sum(w[i] / rho[i] * alpha[i] for i in w)
    den = sum(w[i] / rho[i] * kappa[i] for i in w)
    return T * num ** 2 / den


# ------------------------------------------------------------ Peng-Robinson mixing (Eqs. 17-18)
def mix_pr(x, params, kij):
    """a_m, a_m', a_m'', b_m with the van der Waals one-fluid rule."""
    am = dam = d2am = 0.0
    for i in x:
        for j in x:
            k = 0.0 if i == j else kij.get((i, j), kij.get((j, i), 0.0))
            ai, aj = params[i], params[j]
            p = ai["a"] * aj["a"]
            dp = ai["da"] * aj["a"] + ai["a"] * aj["da"]
            d2p = ai["d2a"] * aj["a"] + 2.0 * ai["da"] * aj["da"] + ai["a"] * aj["d2a"]
            g = math.sqrt(p)
            f = x[i] * x[j] * (1.0 - k)
            am += f * g
            dam += f * dp / (2.0 * g)
            d2am += f * (d2p / (2.0 * g) - dp ** 2 / (4.0 * g ** 3))
    return {"a": am, "da": dam, "d2a": d2am, "b": sum(x[i] * params[i]["b"] for i in x)}

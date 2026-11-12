"""Whole sample (spec Sec. 3.6): phase fractions, apparent c_p and c_v."""


def volume_to_mass(phi, rho):
    """Eq. 20: w_k = phi_k rho_k / sum phi_j rho_j. Returns (w, rho_s)."""
    rho_s = sum(phi[k] * rho[k] for k in phi)
    return {k: phi[k] * rho[k] / rho_s for k in phi}, rho_s


def mass_to_volume(w, rho):
    """phi_k = (w_k/rho_k) / sum w_j/rho_j. Returns (phi, rho_s)."""
    v = sum(w[k] / rho[k] for k in w)
    return {k: (w[k] / rho[k]) / v for k in w}, 1.0 / v


def cp_apparent(w, cp):
    """Eq. 2/20: c_p,app = sum w_k c_p,k."""
    return sum(w[k] * cp[k] for k in w)


def cp_volume_weighted(phi, cp):
    """Pak-Cho form sum phi_k c_p,k: diagnostic only (mixes per-mass and volume)."""
    return sum(phi[k] * cp[k] for k in phi)


def cp_minus_cv_sample(T, phi, alpha, kappa, rho_s):
    """Eq. 21: c_p,app - c_v,app = T (sum phi alpha)^2 / (rho_s sum phi kappa)."""
    a = sum(phi[k] * alpha[k] for k in phi)
    b = sum(phi[k] * kappa[k] for k in phi)
    return T * a ** 2 / (rho_s * b)


def cv_gap(T, phi, alpha, kappa, rho_s):
    """Eq. 23: c_v,app - sum w c_v,k (>= 0) from Lagrange's identity."""
    keys = list(phi)
    s = 0.0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            s += phi[a] * phi[b] * kappa[a] * kappa[b] * (alpha[a] / kappa[a] - alpha[b] / kappa[b]) ** 2
    return T / (rho_s * sum(phi[k] * kappa[k] for k in keys)) * s

from __future__ import annotations

from dataclasses import dataclass
from math import exp, factorial, floor, log, log2, sqrt

from qkd_lab.math_utils import h2
from qkd_lab.models import CountRecord, IntensitySetting


@dataclass(frozen=True)
class Lim2014Result:
    secure_bits: int
    abort: bool
    s_x0_lower: float
    s_x1_lower: float
    s_z1_lower: float
    v_z1_upper: float
    phase_error_upper: float
    leak_ec: int
    eps_sec: float
    eps_cor: float


def tau_n(intensities: tuple[IntensitySetting, ...], n: int) -> float:
    return sum(x.probability * exp(-x.mu) * x.mu**n / factorial(n) for x in intensities)


def _n_pm(count: int, basis_total: int, setting: IntensitySetting, eps_sec: float) -> tuple[float, float]:
    radius = sqrt(basis_total / 2.0 * log(21.0 / eps_sec))
    scale = exp(setting.mu) / setting.probability
    return scale * max(0.0, count - radius), scale * (count + radius)


def _m_pm(count: int, error_total: int, setting: IntensitySetting, eps_sec: float) -> tuple[float, float]:
    radius = sqrt(error_total / 2.0 * log(21.0 / eps_sec)) if error_total > 0 else 0.0
    scale = exp(setting.mu) / setting.probability
    return scale * max(0.0, count - radius), scale * (count + radius)


def _ordered_three(intensities: tuple[IntensitySetting, ...]) -> tuple[IntensitySetting, IntensitySetting, IntensitySetting]:
    if len(intensities) != 3:
        raise ValueError("Lim-2014 analytical backend requires exactly three intensities")
    mu1, mu2, mu3 = sorted(intensities, key=lambda x: x.mu, reverse=True)
    if not (mu1.mu > mu2.mu > mu3.mu >= 0.0):
        raise ValueError("require mu1 > mu2 > mu3 >= 0")
    if not mu1.mu > mu2.mu + mu3.mu:
        raise ValueError("Lim-2014 analytical condition requires mu1 > mu2 + mu3")
    return mu1, mu2, mu3


def _vacuum_single_bounds(
    basis: str,
    records: dict[tuple[str, str], CountRecord],
    intensities: tuple[IntensitySetting, ...],
    eps_sec: float,
) -> tuple[float, float]:
    mu1, mu2, mu3 = _ordered_three(intensities)
    n_total = sum(records[(basis, x.name)].detected for x in intensities)
    if n_total <= 0:
        return 0.0, 0.0

    n1_minus, n1_plus = _n_pm(records[(basis, mu1.name)].detected, n_total, mu1, eps_sec)
    n2_minus, n2_plus = _n_pm(records[(basis, mu2.name)].detected, n_total, mu2, eps_sec)
    n3_minus, n3_plus = _n_pm(records[(basis, mu3.name)].detected, n_total, mu3, eps_sec)

    t0 = tau_n(intensities, 0)
    t1 = tau_n(intensities, 1)

    # Eq. (2), Lim et al. PRA 89, 022307 (2014).
    s0 = t0 * (mu2.mu * records[(basis, mu3.name)].detected - mu3.mu * n2_plus) / (mu2.mu - mu3.mu)
    s0 = max(0.0, s0)

    denom = mu1.mu * (mu2.mu - mu3.mu) - mu2.mu**2 + mu3.mu**2
    bracket = n2_minus - n3_plus - ((mu2.mu**2 - mu3.mu**2) / mu1.mu**2) * (n1_plus - s0 / max(t0, 1e-30))
    s1 = t1 * mu1.mu * bracket / denom
    return max(0.0, s0), max(0.0, s1)


def _single_photon_error_upper_z(
    records: dict[tuple[str, str], CountRecord],
    intensities: tuple[IntensitySetting, ...],
    eps_sec: float,
) -> float:
    _, mu2, mu3 = _ordered_three(intensities)
    m_total = sum(records[("Z", x.name)].errors for x in intensities)
    if m_total <= 0:
        return 0.0
    _, m2_plus = _m_pm(records[("Z", mu2.name)].errors, m_total, mu2, eps_sec)
    m3_minus, _ = _m_pm(records[("Z", mu3.name)].errors, m_total, mu3, eps_sec)
    t1 = tau_n(intensities, 1)
    value = t1 * (m2_plus - m3_minus) / (mu2.mu - mu3.mu)
    return max(0.0, value)


def gamma_lim2014(a: float, b: float, c: float, d: float) -> float:
    """Eq. (5) finite-sampling term from Lim et al. 2014.

    a=eps_sec, b=single-photon bit-error estimate in test basis,
    c=s_Z,1 and d=s_X,1 in the paper notation used here.
    """
    if c <= 0.0 or d <= 0.0:
        return 0.5
    b = min(1.0 - 1e-15, max(1e-15, b))
    prefactor = (c + d) * (1.0 - b) * b / (c * d * log(2.0))
    inside = (c + d) / (c * d * (1.0 - b) * b) * (21.0**2 / a**2)
    if inside <= 1.0:
        return 0.0
    return sqrt(max(0.0, prefactor * log2(inside)))


def estimate_lim2014(
    records: dict[tuple[str, str], CountRecord],
    intensities: tuple[IntensitySetting, ...],
    *,
    eps_sec: float,
    eps_cor: float,
    leak_ec: int | None = None,
    f_ec: float = 1.16,
) -> Lim2014Result:
    if not 0.0 < eps_sec < 1.0 or not 0.0 < eps_cor < 1.0:
        raise ValueError("security parameters must lie in (0,1)")

    s_x0, s_x1 = _vacuum_single_bounds("X", records, intensities, eps_sec)
    _, s_z1 = _vacuum_single_bounds("Z", records, intensities, eps_sec)
    v_z1 = _single_photon_error_upper_z(records, intensities, eps_sec)

    if s_z1 <= 0.0 or s_x1 <= 0.0:
        phi = 0.5
    else:
        e_z1 = min(0.5, v_z1 / s_z1)
        phi = min(0.5, e_z1 + gamma_lim2014(eps_sec, e_z1, s_z1, s_x1))

    x_total = sum(records[("X", x.name)].detected for x in intensities)
    x_errors = sum(records[("X", x.name)].errors for x in intensities)
    qber_x = x_errors / x_total if x_total else 0.5
    if leak_ec is None:
        leak_ec = int(max(0.0, f_ec * x_total * h2(min(0.5, qber_x))))

    finite_penalty = 6.0 * log2(21.0 / eps_sec) + log2(2.0 / eps_cor)
    ell = s_x0 + s_x1 * (1.0 - h2(phi)) - leak_ec - finite_penalty
    secure_bits = max(0, floor(ell))

    return Lim2014Result(
        secure_bits=secure_bits,
        abort=(secure_bits <= 0 or phi >= 0.5),
        s_x0_lower=s_x0,
        s_x1_lower=s_x1,
        s_z1_lower=s_z1,
        v_z1_upper=v_z1,
        phase_error_upper=phi,
        leak_ec=int(leak_ec),
        eps_sec=eps_sec,
        eps_cor=eps_cor,
    )
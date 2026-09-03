from __future__ import annotations

from dataclasses import dataclass
from math import exp, floor, log, log2, sqrt

from qkd_lab.estimation.confidence import ProbabilityInterval, clopper_pearson_interval
from qkd_lab.estimation.mdi_decoy_lp import MDIDecoyBounds, estimate_mdi_bounds
from qkd_lab.math_utils import h2
from qkd_lab.models import IntensitySetting
from qkd_lab.protocols.mdi_qkd import MDIBlock


@dataclass(frozen=True)
class MDIFiniteKeyBudget:
    failure_probability: float
    eps_cor: float
    eps_prime: float
    eps_hat: float
    eps_e: float
    eps_b: float
    eps_0: float
    eps_1: float
    eps_pa: float

    @property
    def eps_sec(self) -> float:
        return 2.0 * (self.eps_prime + 2.0 * self.eps_e + self.eps_hat) + self.eps_b + self.eps_0 + self.eps_1 + self.eps_pa


@dataclass(frozen=True)
class MDIFiniteKeyResult:
    secure_bits: int
    abort: bool
    y11_lower: float
    e11_upper: float
    n11_lower: float
    phase_error_upper: float
    leak_ec: int
    eps_sec: float
    eps_cor: float


def _signal(items: tuple[IntensitySetting, ...]) -> IntensitySetting:
    return max(items, key=lambda x: x.mu)


def _finite_intervals(block: MDIBlock, basis: str, failure_probability: float) -> tuple[list[tuple[float, float]], list[ProbabilityInterval], list[ProbabilityInterval]]:
    pairs = [(a, b) for a in block.alice_intensities for b in block.bob_intensities]
    groups = max(1, 2 * len(pairs))
    per = failure_probability / groups
    mus: list[tuple[float, float]] = []
    gains: list[ProbabilityInterval] = []
    errors: list[ProbabilityInterval] = []
    for a, b in pairs:
        rec = block.records[(basis, a.name, b.name)]
        if rec.sent <= 0:
            continue
        mus.append((a.mu, b.mu))
        gains.append(clopper_pearson_interval(rec.detected, rec.sent, per))
        errors.append(clopper_pearson_interval(rec.errors, rec.sent, per))
    return mus, gains, errors


def estimate_mdi_finite_key(
    block: MDIBlock,
    budget: MDIFiniteKeyBudget,
    *,
    f_ec: float = 1.16,
    n_max: int = 6,
) -> MDIFiniteKeyResult:
    mus, gains, error_gains = _finite_intervals(block, "X", budget.failure_probability)
    bounds: MDIDecoyBounds = estimate_mdi_bounds(mus, gains, error_gains, n_max=n_max)

    a_sig = _signal(block.alice_intensities)
    b_sig = _signal(block.bob_intensities)
    key_rec = block.records[("Z", a_sig.name, b_sig.name)]

    p11 = exp(-a_sig.mu) * a_sig.mu * exp(-b_sig.mu) * b_sig.mu
    mean_n11 = key_rec.sent * p11 * bounds.y11_lower
    count_penalty = sqrt(max(0.0, key_rec.sent / 2.0 * log(1.0 / budget.eps_1)))
    n11_lower = max(0.0, mean_n11 - count_penalty)

    if n11_lower <= 0.0 or bounds.e11_upper >= 0.5:
        phase_error = 0.5
    else:
        sampling_penalty = sqrt(log(1.0 / budget.eps_e) / (2.0 * n11_lower))
        phase_error = min(0.5, bounds.e11_upper + sampling_penalty)

    leak_ec = int(max(0.0, f_ec * key_rec.detected * h2(min(0.5, key_rec.qber))))

    # Conservative Curty-2014-style expression: the positive vacuum term n_{k,0}
    # is deliberately omitted (set to zero). The finite correction form follows
    # the MDI finite-key result commonly written as Eq. (15) in later summaries of
    # Curty et al. 2014.
    correction = (
        log2(8.0 / budget.eps_cor)
        + 2.0 * log2(2.0 / (budget.eps_prime**2 * budget.eps_hat))
        + 2.0 * log2(1.0 / (2.0 * budget.eps_pa))
    )
    ell = n11_lower * (1.0 - h2(phase_error)) - leak_ec - correction
    secure_bits = max(0, floor(ell))

    return MDIFiniteKeyResult(
        secure_bits=secure_bits,
        abort=(secure_bits <= 0 or phase_error >= 0.5),
        y11_lower=bounds.y11_lower,
        e11_upper=bounds.e11_upper,
        n11_lower=n11_lower,
        phase_error_upper=phase_error,
        leak_ec=leak_ec,
        eps_sec=budget.eps_sec,
        eps_cor=budget.eps_cor,
    )
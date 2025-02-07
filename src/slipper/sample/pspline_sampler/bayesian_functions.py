import numpy as np
from bilby.core.prior import ConditionalPriorDict, Gamma


def _vPv(v, P):
    return np.dot(np.dot(v.T, P), v)


def lprior(k, v, τ, τα, τβ, φ, φα, φβ, δ, δα, δβ, P):
    # TODO: Move to using bilby priors

    vTPv = _vPv(v, P)
    logφ = np.log(φ)
    logδ = np.log(δ)
    logτ = np.log(τ)

    lnpri_weights = (k - 1) * logφ * 0.5 - φ * vTPv * 0.5
    lnpri_φ = φα * logδ + (φα - 1) * logφ - φβ * δ * φ
    lnpri_δ = (δα - 1) * logδ - δβ * δ
    lnpri_τ = -(τα + 1) * logτ - τβ / τ
    log_prior = lnpri_weights + lnpri_φ + lnpri_δ + lnpri_τ
    return log_prior


def φ_prior(k, v, P, φα, φβ, δ):
    vTPv = np.dot(np.dot(v.T, P), v)
    shape = (k - 1) / 2 + φα
    rate = φβ * δ + vTPv / 2
    return Gamma(k=shape, theta=1 / rate)


def δ_prior(φ, φα, φβ, δα, δβ):
    """Gamma prior for pi(δ|φ)"""
    shape = φα + δα
    rate = φβ * φ + δβ
    return Gamma(k=shape, theta=1 / rate)


def inv_τ_prior(v, data, spline_model, τα, τβ):
    """Inverse(?) prior for tau -- tau = 1/inv_tau_sample"""

    # TODO: ask about the even/odd difference, and what 'bFreq' is

    n = len(data)
    _spline = spline_model(v=v, n=n)
    is_even = n % 2 == 0
    if is_even:
        spline_normed_data = data[1:-1] / _spline[1:-1]
    else:
        spline_normed_data = data[1:] / _spline[1:]

    n = len(spline_normed_data)

    shape = τα + n / 2
    rate = τβ + np.sum(spline_normed_data) / (2 * np.pi) / 2
    return Gamma(k=shape, theta=1 / rate)


def sample_φδτ(k, v, τ, τα, τβ, φ, φα, φβ, δ, δα, δβ, data, spline_model):
    φ = φ_prior(k, v, spline_model.penalty_matrix, φα, φβ, δ).sample().flat[0]
    δ = δ_prior(φ, φα, φβ, δα, δβ).sample().flat[0]
    τ = 1 / inv_τ_prior(v, data, spline_model, τα, τβ).sample()
    return φ, δ, τ


def llike(v, τ, data, spline_model):
    """Whittle log likelihood"""
    # TODO: Move to using bilby likelihood
    # TODO: the parameters to this function should
    #  be the sampling parameters, not the matrix itself!
    # todo: V should be computed in here

    n = len(data)
    _spline = spline_model(v=v, n=n) * τ

    is_even = n % 2 == 0
    if is_even:
        _spline = _spline[1:]
        data = data[1:]
    else:
        _spline = _spline[1:-1]
        data = data[1:-1]

    integrand = np.log(_spline) + data / (_spline * 2 * np.pi)
    lnlike = -np.sum(integrand) / 2
    if not np.isfinite(lnlike):
        raise ValueError(f"lnlike is not finite: {lnlike}")
    return lnlike


def lpost(k, v, τ, τα, τβ, φ, φα, φβ, δ, δα, δβ, data, psline_model):
    logprior = lprior(
        k, v, τ, τα, τβ, φ, φα, φβ, δ, δα, δβ, psline_model.penalty_matrix
    )
    loglike = llike(v, τ, data, psline_model)
    logpost = logprior + loglike
    if not np.isfinite(logpost):
        raise ValueError(
            f"logpost is not finite: lnpri{logprior}, lnlike{loglike}, lnpost{logpost}"
        )

    return logpost

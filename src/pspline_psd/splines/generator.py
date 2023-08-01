import numpy as np
from scipy.interpolate import interp1d


def build_spline_model(v: np.ndarray, db_list: np.ndarray, n: int):
    """Build a spline model from a vector of spline coefficients and a list of B-spline basis functions"""
    unorm_spline = get_unormalised_spline_model(v, db_list)
    return unroll_list_to_new_length(unorm_spline, n)


def get_unormalised_spline_model(v: np.ndarray, db_list: np.ndarray):
    """Compute unnormalised PSD using random mixture of B-splines

    Parameters
    ----------
    v : np.ndarray
        Vector of spline coefficients (length k)

    db_list : np.ndarray
        Matrix of B-spline basis functions (k x n)

    Returns
    -------
    psd : np.ndarray

    """
    v = np.array(v)
    expV = np.exp(v)

    # converting to weights
    # Eq near 4, page 3.1
    if np.any(np.isinf(expV)):
        ls = np.logaddexp(0, v)
        weight = np.exp(v - ls)
    else:
        ls = 1 + np.sum(expV)
        weight = expV / ls

    s = 1 - np.sum(weight)
    # adding last element to weight
    weight = np.append(weight, 0 if s < 0 else s).ravel()

    psd = density_mixture(densities=db_list.T, weights=weight)
    epsilon = 1e-20
    # element wise maximum value bewteen psd and epsilon
    psd = np.maximum(psd, epsilon)
    return psd


def density_mixture(weights: np.ndarray, densities: np.ndarray) -> np.ndarray:
    """build a density mixture, given mixture weights and densities"""
    assert (
        len(weights) == densities.shape[0],
        f"weights ({weights.shape}) and densities ({densities.shape}) must have the same length",
    )
    n = densities.shape[1]
    res = np.zeros(n)
    for i in range(len(weights)):
        for j in range(n):
            res[j] += weights[i] * densities[i, j]
    return res


def unroll_list_to_new_length(qPsd, n):
    """unroll PSD from qPsd to psd of length n"""
    # q = np.zeros(n)
    # q[0] = qPsd[0]
    # N = (n - 1) // 2
    # assert len(qPsd) >= N + 1, f"qPsd ({len(qPsd)}) must have length >= {N + 1}"
    # for i in range(1, N + 1):
    #     j = 2 * i - 1
    #     q[j] = qPsd[i]
    #     q[j + 1] = qPsd[i]
    #
    # q[-1] = qPsd[-1]
    # TODO: is this necessary?

    newx = np.linspace(0, 1, n)
    oldx = np.linspace(0, 1, len(qPsd))
    f = interp1d(oldx, qPsd, kind="nearest")
    q = f(newx)
    assert np.all(q >= 0), f"q must be positive, but got {q}"
    return q

import os
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from pspline_psd.fourier_methods import get_fz, get_periodogram
from pspline_psd.splines import knot_locator

MAKE_PLOTS = True


DIR = Path(__file__).parent
DATA_DIR = DIR / "data"
DATA_PATHS = dict(
    data_0=DATA_DIR / "data_0.Rdata",
    raw_data=DATA_DIR / "data.txt",
    db_list=DATA_DIR / "db_list.txt",
    tau=DATA_DIR / "tau_trace.txt",
    v=DATA_DIR / "v_trace.txt",
    ll=DATA_DIR / "ll_trace.txt",
)


def test_basis_same_as_r_package_basis(helpers):
    """Test that the spline basis generated by this package
    are the same as those generated by the r-package"""
    # load raw data and true db_list
    data = helpers.load_raw_data()
    true_db_list = helpers.load_db_list()

    # generate basis functions
    degree = 3
    k = 32
    τ, δ, φ, fz, periodogram, V, omega = _get_initial_values(data, k)
    knots = knot_locator(data, k=k, degree=degree, eqSpaced=True)
    db_list = dbspline(omega, knots, degree=degree).T

    if MAKE_PLOTS:
        for i in range(k):
            if i == 0:
                plt.plot(true_db_list[i], color="gray", label="True")
                plt.plot(db_list[i], color="red", ls="--", label="Estimated")
            else:
                plt.plot(true_db_list[i], color="gray")
                plt.plot(db_list[i], color="red", ls="--")
        plt.xticks([])
        plt.yticks([])
        plt.title("Basis functions")
        plt.legend()
        plt.tight_layout()
        plt.savefig(f"{helpers.OUTDIR}/basis_comparison.png")

    residuals = np.sum(
        np.array([np.sum(np.abs(true_db_list[i] - db_list[i])) for i in range(k)])
    )
    assert residuals < 1e-5


def load_rdata(path):
    import rpy2.robjects as robjects

    robjects.r["load"](str(path))
    d = dict(data=np.array(robjects.r["data"]))
    d.update(dict(**r_obj_as_dict(robjects.r["mcmc"])))
    return d


def r_obj_as_dict(vector):
    import rpy2.robjects as robjects

    """Convert an RPy2 ListVector to a Python dict"""
    result = {}
    r2np_types = [
        robjects.FloatVector,
        robjects.IntVector,
        robjects.Matrix,
        robjects.vectors.FloatMatrix,
    ]
    for i, name in enumerate(vector.names):
        if isinstance(vector[i], robjects.ListVector):
            result[name] = r_obj_as_dict(vector[i])
        elif len(vector[i]) == 1:
            result[name] = vector[i][0]
        elif type(vector[i]) in r2np_types:
            result[name] = np.array(vector[i])
        else:
            result[name] = vector[i]
    return result


import numpy as np

from pspline_psd.fourier_methods import get_fz, get_periodogram


def test_periodogram(helpers):
    """
    Test that the FFT function works
    """
    data_obj = helpers.load_data_0()
    ar4_data = data_obj["data"]

    ar4_data = ar4_data - np.mean(ar4_data)
    ar4_data = ar4_data / np.std(ar4_data)

    expected_pdgm = data_obj["pdgrm"]
    fz = get_fz(ar4_data)
    py_pdgm = get_periodogram(fz)
    # only keep every 2nd value
    py_pdgm = py_pdgm[::2]
    # add a zero to the end
    py_pdgm = np.append(py_pdgm, 0)

    fig = helpers.plot_comparison(
        expected_pdgm / np.sum(expected_pdgm), py_pdgm / np.sum(py_pdgm), "pdgrm"
    )
    fig.show()
    assert np.allclose(expected_pdgm, py_pdgm, atol=1e-5)


class Helpers:
    SAVE_PLOTS = True
    OUTDIR = mkdir(os.path.join(DIR, "test_output"))

    @staticmethod
    def load_raw_data():
        return np.loadtxt(DATA_PATHS["raw_data"])

    @staticmethod
    def load_data_0():
        return load_rdata(DATA_PATHS["data_0"])

    @staticmethod
    def load_db_list():
        return np.loadtxt(DATA_PATHS["db_list"])

    @staticmethod
    def load_v():
        return np.loadtxt(DATA_PATHS["v"])

    @staticmethod
    def load_ll():
        return np.loadtxt(DATA_PATHS["ll"])

    @staticmethod
    def load_tau():
        return np.loadtxt(DATA_PATHS["tau"])

    @staticmethod
    def plot_comparison(expected, actual, label):
        fig, (ax0, ax1) = plt.subplots(
            2,
            1,
            gridspec_kw={"height_ratios": [3, 1], "wspace": 0, "hspace": 0},
            sharex=True,
        )
        ax0.plot(expected, label="True", color="C0")
        ax0.plot(actual, label="computed", color="C1", ls="--")
        ax0.legend()
        try:
            ax1.errorbar(
                [i for i in range(len(expected))],
                [0] * len(expected),
                yerr=abs(expected - actual),
                fmt=".",
                ms=0.5,
                color="k",
            )
        except Exception as e:
            print(e)
        ax1.set_xlabel("index")
        ax1.set_ylabel(r"$\delta$" + label)
        ax0.set_ylabel(label)
        fig.tight_layout()
        if Helpers.SAVE_PLOTS:
            fig.savefig(os.path.join(Helpers.OUTDIR, f"{label}.png"), dpi=300)
        return fig


@pytest.fixture
def helpers():
    return Helpers


def test_fft(helpers):
    """
    Test that the FFT function works
    """
    data_obj = helpers.load_data_0()
    ar4_data = data_obj["data"]
    expected_fz = data_obj["anSpecif"]["FZ"][1:-2]
    py_fz = get_fz(ar4_data)[1:-2]
    helpers.plot_comparison(expected_fz, py_fz, "FZ")
    assert np.allclose(expected_fz, py_fz, atol=1e-5)


import matplotlib.pyplot as plt
import numpy as np

from pspline_psd.bayesian_utilities import llike, lprior
from pspline_psd.bayesian_utilities.bayesian_functions import _vPv, sample_φδτ
from pspline_psd.fourier_methods import get_fz, get_periodogram
from pspline_psd.sample.spline_model_sampler import (
    _get_initial_spline_data,
    _get_initial_values,
)
from pspline_psd.splines.generator import build_spline_model, unroll_list_to_new_length
from pspline_psd.splines.initialisation import _generate_initial_weights, knot_locator
from pspline_psd.splines.p_splines import PSplines

MAKE_PLOTS = True


def test_psd_unroll():
    ar = unroll_list_to_new_length(np.array([1, 2, 3, 4]), n=8)
    assert np.allclose(ar, np.array([1, 2, 2, 3, 3, 4, 4, 4]))
    ar = unroll_list_to_new_length(np.array([1, 2, 3]), n=6)
    assert np.allclose(ar, np.array([1, 2, 2, 3, 3, 3]))
    ar = unroll_list_to_new_length(np.array([1, 2, 3]), n=5)
    assert np.allclose(ar, np.array([1, 2, 2, 3, 3]))


def test_lprior():
    v = np.array([-68.6346650, 4.4997348, 1.6011013, -0.1020887])
    P = np.array(
        [
            [1e-6, 0.00, 0.0000000000, 0.0000000000],
            [0.00, 1e-6, 0.0000000000, 0.0000000000],
            [0.00, 0.00, 0.6093175700, 0.3906834292],
            [0.00, 0.00, 0.3906834292, 0.3340004330],
        ]
    )
    assert np.isclose(_vPv(v, P), 1.442495205)
    val = lprior(
        k=5,
        v=v,
        τ=0.1591549431,
        τα=0.001,
        τβ=0.001,
        φ=1,
        φα=1,
        φβ=1,
        δ=1,
        δα=1e-04,
        δβ=1e-04,
        P=P,
    )
    assert np.isclose(val, 0.1120841558)


def test_llike(helpers):
    data = helpers.load_raw_data()
    degree = 3
    k = 32
    τ, δ, φ, fz, periodogram, V, omega = _get_initial_values(data, k)
    fz = get_fz(data)

    periodogram = get_periodogram(fz)
    knots = knot_locator(data, k=k, degree=degree, eqSpaced=True)
    spline_model = PSplines(knots, degree=degree)
    llike_val = llike(v=V, τ=τ, pdgrm=periodogram, spline_model=spline_model)
    assert not np.isnan(llike_val)
    psd = spline_model(v=V)
    assert not np.isnan(psd).any()

    ll_vals = helpers.load_ll()
    highest_ll_idx = np.argmax(ll_vals)
    best_V = helpers.load_v()[:, highest_ll_idx]
    best_τ = helpers.load_tau()[highest_ll_idx]
    best_llike_val = llike(
        v=best_V, τ=best_τ, pdgrm=periodogram, spline_model=spline_model
    )

    # assert best_llike_val == ll_vals[highest_ll_idx]
    assert np.abs(llike_val - best_llike_val) < 100
    best_psd = spline_model(v=best_V)

    if MAKE_PLOTS:
        fig = __plot_psd(
            periodogram,
            [psd, best_psd],
            [f"PSD lnl{llike_val:.2f}", f"PSD lnl{best_llike_val:.2f}"],
            spline_model.basis,
        )
        fig.savefig(f"{helpers.OUTDIR}/test_llike.png")
        fig.show()


def __plot_psd(periodogram, psds, labels, db_list):
    plt.plot(periodogram / np.sum(periodogram), label="data", color="k")
    for psd, l in zip(psds, labels):
        plt.plot(psd / np.sum(psd), label=l)
    ylims = plt.gca().get_ylim()
    basis = db_list
    net_val = max(periodogram)

    basis = basis / net_val
    for idx, bi in enumerate(basis.T):
        kwgs = dict(color=f"C{idx + 2}", lw=0.1, zorder=-1)
        if idx == 0:
            kwgs["label"] = "basis"
        bi = unroll_list_to_new_length(bi, n=len(periodogram))
        plt.plot(bi / net_val, **kwgs)
    plt.ylim(*ylims)
    plt.ylabel("PSD")
    plt.legend(loc="upper right")
    return plt.gcf()


def test_sample_prior(helpers):
    data = helpers.load_raw_data()
    data = data - np.mean(data)
    rescale = np.std(data)
    data = data / rescale

    k = 32
    degree = 3
    n = len(data)
    omega = np.linspace(0, 1, n // 2 + 1)
    diffMatrixOrder = 2

    kwargs = {
        "data": data,
        "degree": degree,
        "omega": omega,
        "diffMatrixOrder": diffMatrixOrder,
    }
    τ0, δ0, φ0, fz, periodogram, V0, omega = _get_initial_values(**kwargs)
    db_list, P = _get_initial_spline_data(
        data, k, degree, omega, diffMatrixOrder, eqSpacedKnots=True
    )
    v = _generate_initial_weights(periodogram, k)
    # create dict with k, v, τ, τα, τβ, φ, φα, φβ, δ, δα, δβ, data, db_list, P

    kwargs = dict(
        k=k,
        v=v,
        τ=None,
        τα=0.001,
        τβ=0.001,
        φ=None,
        φα=2,
        φβ=1,
        δ=1,
        δα=1e-4,
        δβ=1e-4,
        periodogram=periodogram,
        db_list=db_list,
        P=P,
    )

    N = 500
    pri_samples = np.zeros((N, 3))
    for i in range(N):
        pri_samples[i, :] = sample_φδτ(**kwargs)

    # plot histogram of pri_samples
    fig, axes = plt.subplots(3, 1, figsize=(10, 10))
    for i in range(3):
        axes[i].hist(pri_samples[:, i], bins=50)
        axes[i].set_xlabel(["φ'", "δ'", "τ'"][i])
    plt.tight_layout()
    plt.show()

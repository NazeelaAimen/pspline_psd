import numpy as np

from slipper.sample.base_sampler import BaseSampler
from slipper.splines.initialisation import knot_locator
from slipper.splines.p_splines import PSplines

from .bayesian_functions import lpost, sample_φδτ


class PsplineSampler(BaseSampler):
    def _init_mcmc(self) -> None:
        """Initialises the self.samples with the itial values of the MCMC"""

        # init model
        sk = self.spline_kwargs
        knots = knot_locator(self.data, self.n_basis, sk["degree"], sk["eqSpaced"])
        self.spline_model = PSplines(
            knots=knots,
            degree=sk["degree"],
            diffMatrixOrder=sk["diffMatrixOrder"],
        )

        # init samples
        self.samples = dict(
            V=np.zeros((self.n_steps, self.n_basis - 1)),
            φ=np.zeros(self.n_steps),
            δ=np.zeros(self.n_steps),
            τ=np.zeros(self.n_steps),
            proposal_sigma=np.zeros(self.n_steps),
            acceptance_fraction=np.zeros(self.n_steps),
        )

        sk = self.sampler_kwargs
        self.samples["τ"][0] = np.var(self.data) / (2 * np.pi)
        self.samples["δ"][0] = sk["δα"] / sk["δβ"]
        self.samples["φ"][0] = sk["φα"] / (sk["φβ"] * self.samples["δ"][0])
        self.samples["V"][0, :] = self.spline_model.guess_initial_v(self.data).ravel()
        self.samples["proposal_sigma"][0] = 1
        self.samples["acceptance_fraction"][0] = 0.4
        self.samples["lpost_trace"] = np.zeros(self.n_steps)

        self.args = [
            self.n_basis,
            self.samples["V"][0],
            self.samples["τ"][0],
            self.sampler_kwargs["τα"],
            self.sampler_kwargs["τβ"],
            self.samples["φ"][0],
            self.sampler_kwargs["φα"],
            self.sampler_kwargs["φβ"],
            self.samples["δ"][0],
            self.sampler_kwargs["δα"],
            self.sampler_kwargs["δβ"],
            self.data,
            self.spline_model,
        ]

    def _mcmc_step(self, itr):
        k = self.n_basis
        aux = np.arange(0, k - 1)
        accept_frac = self.samples["acceptance_fraction"][itr - 1]
        sigma = self.samples["proposal_sigma"][itr - 1]
        np.random.shuffle(aux)

        self.args = [
            self.n_basis,
            self.samples["V"][itr - 1, :],
            self.samples["τ"][itr - 1],
            self.sampler_kwargs["τα"],
            self.sampler_kwargs["τβ"],
            self.samples["φ"][itr - 1],
            self.sampler_kwargs["φα"],
            self.sampler_kwargs["φβ"],
            self.samples["δ"][itr - 1],
            self.sampler_kwargs["δα"],
            self.sampler_kwargs["δβ"],
            self.data,
            self.spline_model,
        ]

        V, τ, φ, δ = self.args[1], self.args[2], self.args[5], self.args[8]
        V_star = self.args[1].copy()
        for _ in range(self.thin):
            lpost_store = lpost(*self.args)
            # 1. explore the parameter space for new V
            V, V_star, accept_frac, sigma = _tune_proposal_distribution(
                aux, accept_frac, sigma, V, V_star, lpost_store, self.args
            )

            # 2. sample new values for φ, δ, τ
            φ, δ, τ = sample_φδτ(*self.args)
            self.args[1] = V
            self.args[2] = τ
            self.args[5] = φ
            self.args[8] = δ

        # 3. store the new values
        self.samples["φ"][itr] = φ
        self.samples["δ"][itr] = δ
        self.samples["τ"][itr] = τ
        self.samples["V"][itr, :] = V
        self.samples["proposal_sigma"][itr] = sigma
        self.samples["acceptance_fraction"][itr] = accept_frac
        self.samples["lpost_trace"][itr] = lpost_store


def _tune_proposal_distribution(
    aux: np.array,
    accept_frac: float,
    sigma: float,
    V: np.array,
    V_star: np.array,
    lpost_store,
    args,
):
    k = args[0]
    k_1 = k - 1

    # tunning proposal distribution
    if accept_frac < 0.30:  # increasing acceptance pbb
        sigma = sigma * 0.90  # decreasing proposal moves
    elif accept_frac > 0.50:  # decreasing acceptance pbb
        sigma = sigma * 1.1  # increasing proposal moves

    accept_count = 0  # ACCEPTANCE PROBABILITY

    # Update "V_store" (weights)
    for g in range(k_1):
        Z = np.random.normal()
        U = np.log(np.random.uniform())

        pos = aux[g]
        V_star[pos] = V[pos] + sigma * Z
        args[1] = V_star  # update V_star
        lpost_star = lpost(*args)

        # is the proposed V_star better than the current V_store?
        alpha1 = np.min(
            [0, (lpost_star - lpost_store).ravel()[0]]
        )  # log acceptance ratio
        if U < alpha1:
            V[pos] = V_star[pos]  # Accept W.star
            lpost_store = lpost_star
            accept_count += 1  # acceptance probability
        else:
            V_star[pos] = V[pos]  # reset proposal value

    accept_frac = accept_count / k_1
    return V, V_star, accept_frac, sigma  # return updated values

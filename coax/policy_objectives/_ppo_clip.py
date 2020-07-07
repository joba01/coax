# ------------------------------------------------------------------------------------------------ #
# MIT License                                                                                      #
#                                                                                                  #
# Copyright (c) 2020, Microsoft Corporation                                                        #
#                                                                                                  #
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software    #
# and associated documentation files (the "Software"), to deal in the Software without             #
# restriction, including without limitation the rights to use, copy, modify, merge, publish,       #
# distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the    #
# Software is furnished to do so, subject to the following conditions:                             #
#                                                                                                  #
# The above copyright notice and this permission notice shall be included in all copies or         #
# substantial portions of the Software.                                                            #
#                                                                                                  #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING    #
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND       #
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,     #
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,   #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.          #
# ------------------------------------------------------------------------------------------------ #

import jax
import jax.numpy as jnp
import haiku as hk

from ..utils import get_magnitude_quantiles
from ._base import PolicyObjective


class PPOClip(PolicyObjective):
    r"""
    PPO-clip policy objective.

    .. math::

        J(\theta; s,a)\ =\ \min\Big(
            \rho_\theta\,\mathcal{A}(s,a)\,,\
            \bar{\rho}_\theta\,\mathcal{A}(s,a)\Big)

    where :math:`\rho_\theta` and :math:`\bar{\rho}_\theta` are the
    bare and clipped probability ratios, respectively:

    .. math::

        \rho_\theta\ =\
            \frac{\pi_\theta(a|s)}{\pi_{\theta_\text{old}}(a|s)}\ ,
        \qquad
        \bar{\rho}_\theta\ =\
            \big[\rho_\theta\big]^{1+\epsilon}_{1-\epsilon}

    This objective has the property that it allows for slightly more off-policy
    updates than the vanilla policy gradient.


    Parameters
    ----------
    pi : Policy

        The parametrized policy :math:`\pi_\theta(a|s)`.

    regularizer : PolicyRegularizer, optional

        A policy regularizer, see :mod:`coax.policy_regularizers`.

    epsilon : positive float, optional

        The clipping parameter :math:`\epsilon` that is used to defined the
        clipped importance weight :math:`\bar{\rho}`.

    """
    REQUIRES_PROPENSITIES = True

    def __init__(self, pi, regularizer=None, epsilon=0.2):

        super().__init__(pi, regularizer)
        self.epsilon = epsilon
        self._init_funcs()

    @property
    def hyperparams(self):
        hparams = getattr(self.regularizer, 'hyperparams', {})
        hparams['epsilon'] = self.epsilon
        return hparams

    def _init_funcs(self):

        def objective_func(params, state, rng, transition_batch, Adv, epsilon):
            rngs = hk.PRNGSequence(rng)

            # get distribution params from function approximator
            S, A, logP = transition_batch[:3]
            dist_params, state_new = self.pi.apply_func(params, state, next(rngs), S, True)

            # compute ppo-clip objective
            X_a = self.pi.action_preprocessor_func(params, next(rngs), A)
            log_pi = self.pi.proba_dist.log_proba(dist_params, X_a)
            ratio = jnp.exp(log_pi - logP)  # logP is log(π_old)
            ratio_clip = jnp.clip(ratio, 1 - epsilon, 1 + epsilon)
            objective = jnp.minimum(Adv * ratio, Adv * ratio_clip)

            # some consistency checks
            assert Adv.ndim == 1
            assert ratio.ndim == 1
            assert ratio_clip.ndim == 1
            assert objective.ndim == 1

            # also pass auxiliary data to avoid multiple forward passes
            return objective, (dist_params, log_pi, state_new)

        def loss_func(params, state, rng, transition_batch, Adv, epsilon, **reg_hparams):
            objective, (dist_params, log_pi, state_new) = \
                objective_func(params, state, rng, transition_batch, Adv, epsilon)

            # flip sign to turn objective into loss
            loss = loss_bare = -jnp.mean(objective)

            # add regularization term
            if self.regularizer is not None:
                loss = loss + jnp.mean(self.regularizer.apply_func(dist_params, **reg_hparams))

            # also pass auxiliary data to avoid multiple forward passes
            return loss, (loss, loss_bare, dist_params, log_pi, state_new)

        def grads_and_metrics_func(
                params, state, rng, transition_batch, Adv, epsilon, **reg_hparams):

            grads, (loss, loss_bare, dist_params, log_pi, state_new) = \
                jax.grad(loss_func, has_aux=True)(
                    params, state, rng, transition_batch, Adv, epsilon, **reg_hparams)

            name = self.__class__.__name__
            metrics = {f'{name}/loss': loss, f'{name}/loss_bare': loss_bare}

            # add sampled KL-divergence of the current policy relative to the behavior policy
            logP = transition_batch.logP  # log-propensities recorded from behavior policy
            metrics[f'{name}/kl_div_old'] = jnp.mean(jnp.exp(logP) * (logP - log_pi))

            # add some diagnostics of the gradients
            metrics.update(get_magnitude_quantiles(grads, key_prefix=f'{name}/grads_'))

            # add regularization metrics
            if self.regularizer is not None:
                metrics.update(self.regularizer.metrics_func(dist_params, **reg_hparams))

            return grads, state_new, metrics

        self._grad_and_metrics_func = jax.jit(grads_and_metrics_func)
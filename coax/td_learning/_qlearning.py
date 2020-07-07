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
from ._base import BaseTD


class QLearning(BaseTD):
    r"""

    TD-learning with q-learning updates. The :math:`n`-step bootstrapped target is constructed as:

    .. math::

        G^{(n)}_t\ =\ R^{(n)}_t + I^{(n)}_t\,\max_a q_\text{targ}(S_{t+n}, a)

    where

    .. math::

        R^{(n)}_t\ &=\ \sum_{k=0}^{n-1}\gamma^kR_{t+k} \\
        I^{(n)}_t\ &=\ \left\{\begin{matrix}
            0           & \text{if $S_{t+n}$ is a terminal state} \\
            \gamma^n    & \text{otherwise}
        \end{matrix}\right.

    Parameters
    ----------
    q : Q

        The main q-function to update.

    q_targ : Q, optional

        The q-function that is used for constructing the TD-target. If this is left unspecified, we
        set ``q_targ = q`` internally.

    loss_function : callable, optional

        The loss function that will be used to regress to the (bootstrapped) target. The loss
        function is expected to be of the form:

        .. math::

            L(y_\text{true}, y_\text{pred})\in\mathbb{R}

        If left unspecified, this defaults to :func:`coax.value_losses.huber`. Check out the
        :mod:`coax.value_losses` module for other predefined loss functions.

    value_transform : ValueTransform or pair of funcs, optional

        If provided, the returns are transformed as follows:

        .. math::

            G^{(n)}_t\ \mapsto\ f\left(G^{(n)}_t\right)\ =\
                f\left(R^{(n)}_t + I^{(n)}_t\,f^{-1}\left(v(S_{t+n})\right)\right)

        where :math:`f` and :math:`f^{-1}` are given by ``value_transform.transform_func`` and
        ``value_transform.inverse_func``, respectively. See :mod:`coax.td_learning` for examples of
        value-transforms. Note that a ValueTransform is just a glorified pair of functions, i.e.
        passing ``value_transform=(func, inverse_func)`` works just as well.

    """
    def __init__(self, q, q_targ=None, loss_function=None, value_transform=None):

        if not q.action_space_is_discrete:
            raise NotImplementedError(
                "QLearning class is only implemented for discrete actions spaces; you can use "
                "QLearningMode non-discrete action spaces")
        super().__init__(
            q=q, q_targ=q_targ, loss_function=loss_function, value_transform=value_transform)
        self._init_funcs()

    def _init_funcs(self):

        def target(params, state, rng, Rn, In, S_next):
            f, f_inv = self.value_transform
            Q_s_next, _ = self.q_targ.apply_func_type2(params, state, rng, S_next, False)
            assert Q_s_next.ndim == 2
            Q_sa_next = jnp.max(Q_s_next, axis=1)
            return f(Rn + In * f_inv(Q_sa_next))

        def loss_func(params, target_params, state, rng, transition_batch):
            rngs = hk.PRNGSequence(rng)
            S, A, _, Rn, In, S_next, _, _ = transition_batch
            G = target(target_params, state, next(rngs), Rn, In, S_next)
            Q, state_new = self.q.apply_func_type1(params, state, next(rngs), S, A, True)
            loss = self.loss_function(G, Q)
            return loss, (loss, G, Q, S, A, state_new)

        def grads_and_metrics_func(params, target_params, state, rng, transition_batch):
            rngs = hk.PRNGSequence(rng)
            grads, (loss, G, Q, S, A, state_new) = \
                jax.grad(loss_func, has_aux=True)(
                    params, target_params, state, next(rngs), transition_batch)

            # target-network estimate
            Q_targ, _ = self.q_targ.apply_func_type1(target_params, state, next(rngs), S, A, False)

            # residuals: estimate - better_estimate
            err = Q - G
            err_targ = Q_targ - Q

            name = self.__class__.__name__
            metrics = {
                f'{name}/loss': loss,
                f'{name}/bias': jnp.mean(err),
                f'{name}/rmse': jnp.sqrt(jnp.mean(jnp.square(err))),
                f'{name}/bias_targ': jnp.mean(err_targ),
                f'{name}/rmse_targ': jnp.sqrt(jnp.mean(jnp.square(err_targ)))}

            # add some diagnostics of the gradients
            metrics.update(get_magnitude_quantiles(grads, key_prefix=f'{name}/grads_'))

            return grads, state_new, metrics

        def td_error_func(params, target_params, state, rng, transition_batch):
            rngs = hk.PRNGSequence(rng)
            S, A, _, Rn, In, S_next, _, _ = transition_batch
            G = target(target_params, state, next(rngs), Rn, In, S_next)
            Q, _ = self.q.apply_func_type1(params, state, next(rngs), S, A, False)
            return G - Q

        self._grads_and_metrics_func = jax.jit(grads_and_metrics_func)
        self._td_error_func = jax.jit(td_error_func)
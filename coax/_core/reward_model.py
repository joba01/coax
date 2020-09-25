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

from .stochastic_q import StochasticQ


__all__ = (
    'RewardModel',
)


class RewardModel(StochasticQ):
    r"""

    A reward function :math:`r(s,a)`, represented by a stochastic function
    :math:`\mathbb{P}_\theta(R_t|S_t=s,A_t=a)`.

    Parameters
    ----------
    func : function

        A Haiku-style function that specifies the forward pass.

    env : gym.Env

        The gym-style environment. This is used to validate the input/output structure of ``func``.

    value_range : tuple of floats

        A pair of floats :code:`(min_value, max_value)`. If left unspecified, this defaults to
        :code:`value_range=env.reward_range`.

    observation_preprocessor : function, optional

        Turns a single observation into a batch of observations that are compatible with the
        corresponding probability distribution. If left unspecified, this defaults to:

        .. code:: python

            observation_preprocessor = ProbaDist(observation_space).preprocess_variate

        See also :attr:`coax.proba_dists.ProbaDist.preprocess_variate`.

    action_preprocessor : function, optional

        Turns a single action into a batch of actions that are compatible with the corresponding
        probability distribution. If left unspecified, this defaults to:

        .. code:: python

            action_preprocessor = ProbaDist(action_space).preprocess_variate

        See also :attr:`coax.proba_dists.ProbaDist.preprocess_variate`.

    value_transform : ValueTransform or pair of funcs, optional

        If provided, the target for the underlying function approximator is transformed:

        .. math::

            \tilde{G}_t\ =\ f(G_t)

        This means that calling the function involves undoing this transformation using its inverse
        :math:`f^{-1}`. The functions :math:`f` and :math:`f^{-1}` are given by
        ``value_transform.transform_func`` and ``value_transform.inverse_func``, respectively. Note
        that a ValueTransform is just a glorified pair of functions, i.e. passing
        ``value_transform=(func, inverse_func)`` works just as well.

    random_seed : int, optional

        Seed for pseudo-random number generators.

    """
    # this is just an alias of StochasticQ

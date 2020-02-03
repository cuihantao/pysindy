import warnings

import numpy as np
from scipy.linalg import cho_factor
from scipy.linalg import cho_solve
from sklearn.exceptions import ConvergenceWarning

from pysindy.optimizers import BaseOptimizer
from pysindy.utils import get_prox


class SR3(BaseOptimizer):
    """
    Sparse relaxed regularized regression.

    Attempts to minimize the objective function
    .. math::

        0.5\\|y-Xw\\|^2_2 + lambda \\times R(v)
        + (0.5 / nu)\\|w-v\\|^2_2

    where R(v) is a regularization function.

    Parameters
    ----------
    threshold : float, optional (default 0.1)
        Determines the strength of the regularization. When the
        regularization function R is the l0 norm, the regularization
        is equivalent to performing hard thresholding, and lambda
        is chosen to threshold at the value given by this parameter.
        This is equivalent to choosing lambda = threshold^2 / (2 * nu).

    nu : float, optional (default 1)
        Determines the level of relaxation. Decreasing nu encourages
        w and v to be close, whereas increasing nu allows the
        regularized coefficients v to be farther from w.

    tol : float, optional (default 1e-5)
        Tolerance used for determining convergence of the optimization
        algorithm.

    thresholder : string, optional (default 'l0')
        Regularization function to use. Currently implemented options
        are 'l0' (l0 norm), 'l1' (l1 norm), and 'cad' (clipped
        absolute deviation).

    max_iter : int, optional (default 30)
        Maximum iterations of the optimization algorithm.

    Attributes
    ----------
    coef_ : array, shape (n_features,) or (n_targets, n_features)
        Regularized weight vector(s). This is the v in the objective
        function.

    coef_full_ : array, shape (n_features,) or (n_targets, n_features)
        Weight vector(s) that are not subjected to the regularization.
        This is the w in the objective function.

    Examples
    --------
    >>> import numpy as np
    >>> from scipy.integrate import odeint
    >>> from pysindy import SINDy
    >>> from pysindy.optimizers import SR3
    >>> lorenz = lambda z,t : [10*(z[1] - z[0]),
    >>>                        z[0]*(28 - z[2]) - z[1],
    >>>                        z[0]*z[1] - 8/3*z[2]]
    >>> t = np.arange(0,2,.002)
    >>> x = odeint(lorenz, [-8,8,27], t)
    >>> opt = SR3(threshold=0.1, nu=1)
    >>> model = SINDy(optimizer=opt)
    >>> model.fit(x, t=t[1]-t[0])
    >>> model.print()
    x0' = -10.004 1 + 10.004 x0
    x1' = 27.994 1 + -0.993 x0 + -1.000 1 x1
    x2' = -2.662 x1 + 1.000 1 x0
    """

    def __init__(
        self, threshold=0.1, nu=1.0, tol=1e-5, thresholder="l0", max_iter=30, **kwargs
    ):
        super(SR3, self).__init__(**kwargs)

        if threshold < 0:
            raise ValueError("threshold cannot be negative")
        if nu <= 0:
            raise ValueError("nu must be positive")
        if tol <= 0:
            raise ValueError("tol must be positive")
        if max_iter <= 0:
            raise ValueError("max_iter must be positive")

        self.threshold = threshold
        self.nu = nu
        self.tol = tol
        self.thresholder = thresholder
        self.prox = get_prox(thresholder)
        self.max_iter = max_iter

    def _update_full_coef(self, cho, x_transpose_y, coef_sparse):
        """Update the unregularized weight vector
        """
        b = x_transpose_y + coef_sparse / self.nu
        coef_full = cho_solve(cho, b)
        self.iters += 1
        return coef_full

    def _update_sparse_coef(self, coef_full):
        """Update the regularized weight vector
        """
        coef_sparse = self.prox(coef_full, self.threshold)
        self.history_.append(coef_sparse)
        return coef_sparse

    def _convergence_criterion(self):
        """Calculate the convergence criterion for the optimization
        """
        this_coef = self.history_[-1]
        if len(self.history_) > 1:
            last_coef = self.history_[-2]
        else:
            last_coef = np.zeros_like(this_coef)
        return np.sum((this_coef - last_coef) ** 2)

    def _reduce(self, x, y):
        """
        Iterates the thresholding. Assumes an initial guess
        is saved in self.coef_ and self.ind_
        """
        coef_sparse = self.coef_
        n_samples, n_features = x.shape

        # Precompute some objects for upcoming least-squares solves.
        # Assumes that self.nu is fixed throughout optimization procedure.
        cho = cho_factor(np.dot(x.T, x) + np.diag(np.full(x.shape[1], 1.0 / self.nu)))
        x_transpose_y = np.dot(x.T, y)

        for _ in range(self.max_iter):
            coef_full = self._update_full_coef(cho, x_transpose_y, coef_sparse)
            coef_sparse = self._update_sparse_coef(coef_full)

            if self._convergence_criterion() < self.tol:
                # Could not (further) select important features
                break
        else:
            warnings.warn(
                "SR3._reduce did not converge after {} iterations.".format(
                    self.max_iter
                ),
                ConvergenceWarning,
            )

        self.coef_ = coef_sparse
        self.coef_full_ = coef_full
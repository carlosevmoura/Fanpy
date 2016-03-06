from __future__ import absolute_import, division, print_function

import numpy as np
from ..lib import base


class Base(object):
    """
    The base class for wavefunctions.
    See `prowl.lib.base`.

    """

    # Bounds
    bounds = (-np.inf, np.inf)

    # Bind methods
    __init__ = base.__init__
    energy = base.energy
    solve = base.solve
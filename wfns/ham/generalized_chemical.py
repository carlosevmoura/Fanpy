r"""Hamiltonian used to describe a chemical system expressed wrt generalized orbitals."""
import numpy as np
from wfns.backend import slater, math_tools
from wfns.ham.generalized_base import BaseGeneralizedHamiltonian


class GeneralizedChemicalHamiltonian(BaseGeneralizedHamiltonian):
    r"""Hamiltonian used to describe a typical chemical system expressed wrt generalized orbitals.

    .. math::

        \hat{H} = \sum_{ij} h_{ij} a^\dagger_i a_j
        + \frac{1}{2} \sum_{ijkl} g_{ijkl} a^\dagger_i a^\dagger_j a_l a_k

    where :math:`h_{ik}` is the one-electron integral and :math:`g_{ijkl}` is the two-electron
    integral in Physicists' notation.

    Attributes
    ----------
    energy_nuc_nuc : float
        Nuclear-nuclear repulsion energy.
    one_int : np.ndarray(K, K)
        One-electron integrals.
    two_int : np.ndarray(K, K, K, K)
        Two-electron integrals.
    params : np.ndarray
        Significant elements of the anti-Hermitian matrix.

    Properties
    ----------
    dtype : {np.float64, np.complex128}
        Data type of the Hamiltonian.
    nspin : int
        Number of spin orbitals.
    nparams : int
        Number of parameters.

    Methods
    -------
    __init__(self, one_int, two_int, orbtype=None, energy_nuc_nuc=None)
        Initialize the Hamiltonian
    assign_energy_nuc_nuc(self, energy_nuc_nuc=None)
        Assigns the nuclear nuclear repulsion.
    assign_integrals(self, one_int, two_int)
        Assign the one- and two-electron integrals.
    orb_rotate_jacobi(self, jacobi_indices, theta)
        Rotate orbitals using Jacobi matrix.
    orb_rotate_matrix(self, matrix)
        Rotate orbitals using a transformation matrix.
    clear_cache(self)
        Placeholder function that would clear the cache.
    assign_params(self, params)
        Transform the integrals with a unitary matrix that corresponds to the given parameters.
    _update_integrals(self, wfn, sd, sd_m, wfn_deriv, ham_deriv, one_electron, coulomb, exchange)
        Update integrals for the given Slater determinant.
        Used to simplify `integrate_wfn_sd`.
    integrate_wfn_sd(self, wfn, sd, wfn_deriv=None, ham_deriv=None)
        Integrate the Hamiltonian with against a wavefunction and Slater determinant.
    integrate_sd_sd(self, sd1, sd2, sign=None, deriv=None)
        Integrate the Hamiltonian with against two Slater determinants.

    """
    def __init__(self, one_int, two_int, energy_nuc_nuc=None, params=None):
        """Initialize the Hamiltonian.

        Parameters
        ----------
        one_int : np.ndarray(K, K)
            One electron integrals.
        two_int : np.ndarray(K, K, K, K)
            Two electron integrals.
        energy_nuc_nuc : {float, None}
            Nuclear nuclear repulsion energy.
            Default is `0.0`.

        """
        super().__init__(one_int, two_int, energy_nuc_nuc=energy_nuc_nuc)
        self.set_ref_ints()
        self.assign_params(params=params)

    def set_ref_ints(self):
        """Store the current integrals as the reference from which orbitals will be rotated."""
        self._ref_one_int = np.copy(self.one_int)
        self._ref_two_int = np.copy(self.two_int)

    def assign_params(self, params=None):
        """Transform the integrals with a unitary matrix that corresponds to the given parameters.

        Parameters
        ----------
        params : {np.ndarray, None}
            Significant elements of the anti-Hermitian matrix. Integrals will be transformed with
            the Unitary matrix that corresponds to the anti-Hermitian matrix.

        Raises
        ------
        ValueError
            If parameters is not a one-dimensional numpy array with K*(K-1)/2 elements, where K is
            the number of orbitals.

        """
        num_orbs = self.one_int.shape[0]
        num_params = num_orbs * (num_orbs - 1) // 2

        if params is None:
            params = np.zeros(num_params)

        if not (isinstance(params, np.ndarray) and params.ndim == 1 and params.size == num_params):
            raise ValueError('Parameters for orbital rotation must be a one-dimension numpy array '
                             'with {0}=K*(K-1)/2 elements, where K is the number of '
                             'orbitals.'.format(num_params))

        # assign parameters
        self.params = params

        # revert integrals back to original
        self.assign_integrals(np.copy(self._ref_one_int), np.copy(self._ref_two_int))

        # convert antihermitian part to unitary matrix.
        unitary = math_tools.unitary_matrix(params)

        # transform integrals
        self.orb_rotate_matrix(unitary)

    def _update_integrals(self, wfn, sd, sd_m, wfn_deriv, ham_deriv, one_electron, coulomb,
                          exchange):
        r"""Add the one-electron, coulomb, and exchange terms of the given Slater determinant.

        Add the term :math:`f(\mathbf{m}) \left< \Phi \middle| \hat{H} \middle| \mathbf{m} \right>`
        to the provided integrals.

        Parameters
        ----------
        wfn : BaseWavefunction
            Wavefunction.
        sd : int
            Slater determinant.
        sd_m : int
            Slater determinant.
        wfn_deriv : {int, None}
            Index of the wavefunction parameter against which the integral is derivatized.
            `None` results in no derivatization.
        ham_deriv : {int, None}
            Index of the Hamiltonian parameter against which the integral is derivatized.
            `None` results in no derivatization.
        one_electron : float
            One-electron energy.
        coulomb : float
            Coulomb energy.
        exchange : float
            Exchange energy.

        Returns
        -------
        one_electron : float
            Updated one-electron energy.
        coulomb : float
            Updated coulomb energy.
        exchange : float
            Updated exchange energy.

        """
        coeff = wfn.get_overlap(sd_m, deriv=wfn_deriv)
        sd_energy = self.integrate_sd_sd(sd, sd_m, deriv=ham_deriv)
        one_electron += coeff * sd_energy[0]
        coulomb += coeff * sd_energy[1]
        exchange += coeff * sd_energy[2]
        return one_electron, coulomb, exchange

    # FIXME: need to speed up
    # TODO: change to integrate_sd_wfn
    def integrate_wfn_sd(self, wfn, sd, wfn_deriv=None, ham_deriv=None):
        r"""Integrate the Hamiltonian with against a wavefunction and Slater determinant.

        .. math::

            \left< \Phi \middle| \hat{H} \middle| \Psi \right>
            = \sum_{\mathbf{m} \in S_\Phi}
              f(\mathbf{m}) \left< \Phi \middle| \hat{H} \middle| \mathbf{m} \right>

        where :math:`\Psi` is the wavefunction, :math:`\hat{H}` is the Hamiltonian operator, and
        :math:`\Phi` is the Slater determinant. The :math:`S_{\Phi}` is the set of Slater
        determinants for which :math:`\left< \Phi \middle| \hat{H} \middle| \mathbf{m} \right>` is
        not zero, which are the :math:`\Phi` and its first and second order excitations for a
        chemical Hamiltonian.

        Parameters
        ----------
        wfn : Wavefunction
            Wavefunction against which the Hamiltonian is integrated.
            Needs to have the following in `__dict__`: `get_overlap`.
        sd : int
            Slater Determinant against which the Hamiltonian is integrated.
        wfn_deriv : {int, None}
            Index of the wavefunction parameter against which the integral is derivatized.
            Default is no derivatization.
        ham_deriv : {int, None}
            Index of the Hamiltonian parameter against which the integral is derivatized.
            Default is no derivatization.

        Returns
        -------
        one_electron : float
            One-electron energy.
        coulomb : float
            Coulomb energy.
        exchange : float
            Exchange energy.

        Raises
        ------
        ValueError
            If integral is derivatized to both wavefunction and Hamiltonian parameters.

        """
        if wfn_deriv is not None and ham_deriv is not None:
            raise ValueError('Integral can be derivatized with respect to at most one out of the '
                             'wavefunction and Hamiltonian parameters.')

        sd = slater.internal_sd(sd)
        occ_indices = slater.occ_indices(sd)
        vir_indices = slater.vir_indices(sd, self.nspin)

        one_electron = 0.0
        coulomb = 0.0
        exchange = 0.0

        def update_integrals(sd_m):
            """Wrapped function for updating the integral values."""
            return self._update_integrals(wfn, sd, sd_m, wfn_deriv, ham_deriv,
                                          one_electron, coulomb, exchange)

        one_electron, coulomb, exchange = update_integrals(sd)
        for counter_i, i in enumerate(occ_indices):
            for counter_a, a in enumerate(vir_indices):
                sd_m = slater.excite(sd, i, a)
                one_electron, coulomb, exchange = update_integrals(sd_m)
                for j in occ_indices[counter_i+1:]:
                    for b in vir_indices[counter_a+1:]:
                        sd_m = slater.excite(sd, i, j, b, a)
                        one_electron, coulomb, exchange = update_integrals(sd_m)

        return one_electron, coulomb, exchange

    def integrate_sd_sd(self, sd1, sd2, sign=None, deriv=None):
        r"""Integrate the Hamiltonian with against two Slater determinants.

        .. math::

            H_{\mathbf{m}\mathbf{n}} &=
            \left< \mathbf{m} \middle| \hat{H} \middle| \mathbf{n} \right>\\
            &= \sum_{ij}
               h_{ij} \left< \mathbf{m} \middle| a^\dagger_i a_j \middle| \mathbf{n} \right>
            + \sum_{i<j, k<l} g_{ijkl}
            \left< \mathbf{m} \middle| a^\dagger_i a^\dagger_j a_l a_k \middle| \mathbf{n} \right>\\

        In the first summation involving :math:`h_{ij}`, only the terms where :math:`\mathbf{m}` and
        :math:`\mathbf{n}` are different by at most single excitation will contribute to the
        integral. In the second summation involving :math:`g_{ijkl}`, only the terms where
        :math:`\mathbf{m}` and :math:`\mathbf{n}` are different by at most double excitation will
        contribute to the integral.

        Parameters
        ----------
        sd1 : int
            Slater Determinant against which the Hamiltonian is integrated.
        sd2 : int
            Slater Determinant against which the Hamiltonian is integrated.
        sign : {1, -1, None}
            Sign change resulting from cancelling out the orbitals shared between the two Slater
            determinants.
            Computes the sign if none is provided.
            Make sure that the provided sign is correct. It will not be checked to see if its
            correct.
        deriv : {int, None}
            Index of the Hamiltonian parameter against which the integral is derivatized.
            Default is no derivatization.

        Returns
        -------
        one_electron : float
            One-electron energy.
        coulomb : float
            Coulomb energy.
        exchange : float
            Exchange energy.

        Raises
        ------
        ValueError
            If `sign` is not `1`, `-1` or `None`.
        NotImplementedError
            If `deriv` is not `None`.

        """
        if deriv is not None:
            raise NotImplementedError('Orbital rotation is not implemented properly: you cannot '
                                      'take the derivative of CI matrix elements with respect to '
                                      'orbital rotation coefficients.')

        sd1 = slater.internal_sd(sd1)
        sd2 = slater.internal_sd(sd2)
        shared_indices = slater.shared_orbs(sd1, sd2)
        diff_sd1, diff_sd2 = slater.diff_orbs(sd1, sd2)
        # if two Slater determinants do not have the same number of electrons
        if len(diff_sd1) != len(diff_sd2):
            return 0.0, 0.0, 0.0
        diff_order = len(diff_sd1)
        if diff_order > 2:
            return 0.0, 0.0, 0.0

        if sign is None:
            sign = slater.sign_excite(sd1, diff_sd1, reversed(diff_sd2))
        elif sign not in [1, -1]:
            raise ValueError('The sign associated with the integral must be either `1` or `-1`.')

        one_electron, coulomb, exchange = 0.0, 0.0, 0.0

        # two sd's are the same
        if diff_order == 0:
            one_electron = np.sum(self.one_int[shared_indices, shared_indices])
            coulomb = np.sum(np.triu(self.two_int[shared_indices, :, shared_indices, :]
                                                 [:, shared_indices, shared_indices], k=1))
            exchange = -np.sum(np.triu(self.two_int[shared_indices, :, :, shared_indices]
                                                   [:, shared_indices, shared_indices], k=1))

        # two sd's are different by single excitation
        elif diff_order == 1:
            a, = diff_sd1
            b, = diff_sd2
            one_electron = self.one_int[a, b]
            coulomb = np.sum(self.two_int[shared_indices, a, shared_indices, b])
            exchange = -np.sum(self.two_int[shared_indices, a, b, shared_indices])

        # two sd's are different by double excitation
        else:
            a, b = diff_sd1
            c, d = diff_sd2
            coulomb = self.two_int[a, b, c, d]
            exchange = -self.two_int[a, b, d, c]

        return sign * one_electron, sign * coulomb, sign * exchange
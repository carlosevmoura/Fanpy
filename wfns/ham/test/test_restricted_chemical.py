"""Test wfns.ham.restricted_chemical."""
import numpy as np
from nose.plugins.attrib import attr
from nose.tools import assert_raises
from wfns.ham.restricted_chemical import RestrictedChemicalHamiltonian
from wfns.tools import find_datafile
from wfns.backend.sd_list import sd_list


class TestWavefunction(object):
    """Mock wavefunction for testing."""
    def get_overlap(self, sd, deriv=None):
        """Get overlap of wavefunction with Slater determinant."""
        if sd == 0b0101:
            return 1
        elif sd == 0b1010:
            return 2
        elif sd == 0b1100:
            return 3
        return 0


def test_integrate_sd_sd_trivial():
    """Test RestrictedChemicalHamiltonian.integrate_sd_sd for trivial cases."""
    one_int = np.random.rand(3, 3)
    two_int = np.random.rand(3, 3, 3, 3)
    test = RestrictedChemicalHamiltonian(one_int, two_int)

    assert_raises(ValueError, test.integrate_sd_sd, 0b001001, 0b100100, sign=0, deriv=None)
    assert_raises(ValueError, test.integrate_sd_sd, 0b001001, 0b100100, sign=0.5, deriv=None)
    assert_raises(ValueError, test.integrate_sd_sd, 0b001001, 0b100100, sign=-0.5, deriv=None)

    assert (0, 0, 0) == test.integrate_sd_sd(0b000111, 0b001001)
    assert (0, 0, 0) == test.integrate_sd_sd(0b000111, 0b111000)
    assert (0, two_int[0, 1, 1, 0], 0) == test.integrate_sd_sd(0b110001, 0b101010, sign=1)
    assert (0, -two_int[0, 1, 1, 0], 0) == test.integrate_sd_sd(0b110001, 0b101010, sign=-1)
    assert (0,
            -two_int[1, 1, 1, 0] - two_int[0, 1, 1, 1]
            + two_int[0, 0, 1, 0] + two_int[0, 1, 0, 0],
            0) == test.integrate_sd_sd(0b110001, 0b101010, sign=1, deriv=0)


def test_integrate_sd_sd_h2_631gdp():
    """Test RestrictedChemicalHamiltonian.integrate_sd_sd using H2 HF/6-31G** orbitals.

    Compare CI matrix with the PySCF result.

    """
    one_int = np.load(find_datafile('test/h2_hf_631gdp_oneint.npy'))
    two_int = np.load(find_datafile('test/h2_hf_631gdp_twoint.npy'))
    ham = RestrictedChemicalHamiltonian(one_int, two_int)

    ref_ci_matrix = np.load(find_datafile('test/h2_hf_631gdp_cimatrix.npy'))
    ref_pspace = np.load(find_datafile('test/h2_hf_631gdp_civec.npy'))

    for i, sd1 in enumerate(ref_pspace):
        for j, sd2 in enumerate(ref_pspace):
            sd1, sd2 = int(sd1), int(sd2)
            assert np.allclose(sum(ham.integrate_sd_sd(sd1, sd2)), ref_ci_matrix[i, j])


def test_integrate_sd_sd_lih_631g_case():
    """Test RestrictedChemicalHamiltonian.integrate_sd_sd using sd's of LiH HF/6-31G orbitals."""
    one_int = np.load(find_datafile('test/lih_hf_631g_oneint.npy'))
    two_int = np.load(find_datafile('test/lih_hf_631g_twoint.npy'))
    ham = RestrictedChemicalHamiltonian(one_int, two_int)

    sd1 = 0b0000000001100000000111
    sd2 = 0b0000000001100100001001
    assert (0, two_int[1, 2, 3, 8], -two_int[1, 2, 8, 3]) == ham.integrate_sd_sd(sd1, sd2)


@attr('slow')
def test_integrate_sd_sd_lih_631g_full():
    """Test RestrictedChemicalHamiltonian.integrate_sd_sd using LiH HF/6-31G orbitals.

    Compared to all of the CI matrix.

    """
    one_int = np.load(find_datafile('test/lih_hf_631g_oneint.npy'))
    two_int = np.load(find_datafile('test/lih_hf_631g_twoint.npy'))
    ham = RestrictedChemicalHamiltonian(one_int, two_int)

    ref_ci_matrix = np.load(find_datafile('test/lih_hf_631g_cimatrix.npy'))
    ref_pspace = np.load(find_datafile('test/lih_hf_631g_civec.npy'))

    for i, sd1 in enumerate(ref_pspace):
        for j, sd2 in enumerate(ref_pspace):
            sd1, sd2 = int(sd1), int(sd2)
            assert np.allclose(sum(ham.integrate_sd_sd(sd1, sd2)), ref_ci_matrix[i, j])


def test_integrate_sd_sd_particlenum():
    """Test RestrictedChemicalHamiltonian.integrate_sd_sd and break particle number symmetery."""
    one_int = np.arange(1, 17, dtype=float).reshape(4, 4)
    two_int = np.arange(1, 257, dtype=float).reshape(4, 4, 4, 4)
    ham = RestrictedChemicalHamiltonian(one_int, two_int)
    civec = [0b01, 0b11]

    # \braket{1 | h_{11} | 1}
    assert np.allclose(sum(ham.integrate_sd_sd(civec[0], civec[0])), 1)
    # \braket{12 | H | 1} = 0
    assert np.allclose(sum(ham.integrate_sd_sd(civec[1], civec[0])), 0)
    assert np.allclose(sum(ham.integrate_sd_sd(civec[0], civec[1])), 0)
    # \braket{12 | h_{11} + h_{22} + g_{1212} - g_{1221} | 12}
    assert np.allclose(sum(ham.integrate_sd_sd(civec[1], civec[1])), 4)


def test_integrate_wfn_sd():
    """Test RestrictedChemicalHamiltonian.integrate_wfn_sd."""
    one_int = np.arange(1, 5, dtype=float).reshape(2, 2)
    two_int = np.arange(5, 21, dtype=float).reshape(2, 2, 2, 2)
    test_ham = RestrictedChemicalHamiltonian(one_int, two_int)
    test_wfn = TestWavefunction()

    one_energy, coulomb, exchange = test_ham.integrate_wfn_sd(test_wfn, 0b0101)
    assert one_energy == 1*1 + 1*1
    assert coulomb == 1*5 + 2*8
    assert exchange == 0

    one_energy, coulomb, exchange = test_ham.integrate_wfn_sd(test_wfn, 0b1010)
    assert one_energy == 2*4 + 2*4
    assert coulomb == 1*17 + 2*20
    assert exchange == 0

    one_energy, coulomb, exchange = test_ham.integrate_wfn_sd(test_wfn, 0b0110)
    assert one_energy == 1*3 + 2*2
    assert coulomb == 1*9 + 2*16
    assert exchange == 0

    one_energy, coulomb, exchange = test_ham.integrate_wfn_sd(test_wfn, 0b1100)
    assert one_energy == 1*3 + 3*4
    assert coulomb == 3*10
    assert exchange == -3*11


def test_param_ind_to_rowcol_ind():
    """Test RestrictedChemicalHamiltonian.param_ind_to_rowcol_ind."""
    for n in range(1, 20):
        ham = RestrictedChemicalHamiltonian(np.random.rand(n, n), np.random.rand(n, n, n, n))
        for row_ind in range(n):
            for col_ind in range(row_ind+1, n):
                param_ind = row_ind * n - row_ind*(row_ind+1)/2 + col_ind - row_ind - 1
                assert ham.param_ind_to_rowcol_ind(param_ind) == (row_ind, col_ind)


def test_integrate_sd_sd_deriv():
    """Test RestrictedChemicalHamiltonian._integrate_sd_sd_deriv."""
    one_int = np.arange(1, 5, dtype=float).reshape(2, 2)
    two_int = np.arange(5, 21, dtype=float).reshape(2, 2, 2, 2)
    test_ham = RestrictedChemicalHamiltonian(one_int, two_int)

    assert_raises(ValueError, test_ham._integrate_sd_sd_deriv, 0b0101, 0b0101, 0.0)
    assert_raises(ValueError, test_ham._integrate_sd_sd_deriv, 0b0101, 0b0101, -1)
    assert_raises(ValueError, test_ham._integrate_sd_sd_deriv, 0b0101, 0b0101, 2)
    assert test_ham._integrate_sd_sd_deriv(0b0101, 0b0001, 0) == (0, 0, 0)


def test_integrate_sd_sd_deriv_fdiff_h2_sto6g():
    """Test RestrictedChemicalHamiltonian._integrate_sd_sd_deriv using H2/STO6G.

    Computed derivatives are compared against finite difference of the `integrate_sd_sd`.

    """
    one_int = np.load(find_datafile('test/h2_hf_sto6g_oneint.npy'))
    two_int = np.load(find_datafile('test/h2_hf_sto6g_twoint.npy'))
    test_ham = RestrictedChemicalHamiltonian(one_int, two_int)
    epsilon = 1e-8

    for sd1 in [0b0011, 0b0101, 0b1001, 0b0110, 0b1010, 0b1100]:
        for sd2 in [0b0011, 0b0101, 0b1001, 0b0110, 0b1010, 0b1100]:
            for i in range(test_ham.nparams):
                addition = np.zeros(test_ham.nparams)
                addition[i] = epsilon
                test_ham2 = RestrictedChemicalHamiltonian(one_int, two_int, params=addition)

                finite_diff = (np.array(test_ham2.integrate_sd_sd(sd1, sd2))
                               - np.array(test_ham.integrate_sd_sd(sd1, sd2))) / epsilon
                derivative = test_ham._integrate_sd_sd_deriv(sd1, sd2, i)
                assert np.allclose(finite_diff, derivative, atol=20*epsilon)


# TODO: add test for comparing Unrestricted with Generalized
@attr('slow')
def test_integrate_sd_sd_deriv_fdiff_h4_sto6g():
    """Test RestrictedChemicalHamiltonian._integrate_sd_sd_deriv using H4/STO6G.

    Computed derivatives are compared against finite difference of the `integrate_sd_sd`.

    """
    one_int = np.load(find_datafile('test/h4_square_hf_sto6g_oneint.npy'))
    two_int = np.load(find_datafile('test/h4_square_hf_sto6g_twoint.npy'))

    test_ham = RestrictedChemicalHamiltonian(one_int, two_int)
    epsilon = 1e-8

    sds = sd_list(4, 4, num_limit=None, exc_orders=None)

    assert np.allclose(one_int, one_int.T)
    assert np.allclose(np.einsum('ijkl->jilk', two_int), two_int)
    assert np.allclose(np.einsum('ijkl->klij', two_int), two_int)

    for sd1 in sds:
        for sd2 in sds:
            for i in range(test_ham.nparams):
                addition = np.zeros(test_ham.nparams)
                addition[i] = epsilon
                test_ham2 = RestrictedChemicalHamiltonian(one_int, two_int, params=addition)

                finite_diff = (np.array(test_ham2.integrate_sd_sd(sd1, sd2))
                               - np.array(test_ham.integrate_sd_sd(sd1, sd2))) / epsilon
                derivative = test_ham._integrate_sd_sd_deriv(sd1, sd2, i)
                assert np.allclose(finite_diff, derivative, atol=20*epsilon)


def test_integrate_sd_sd_deriv_fdiff_random():
    """Test RestrictedChemicalHamiltonian._integrate_sd_sd_deriv using random integrals.

    Computed derivatives are compared against finite difference of the `integrate_sd_sd`.

    """
    one_int = np.random.rand(4, 4)
    one_int = one_int + one_int.T

    two_int = np.random.rand(4, 4, 4, 4)
    two_int = np.einsum('ijkl->jilk', two_int) + two_int
    two_int = np.einsum('ijkl->klij', two_int) + two_int

    # check that the in tegrals have the appropriate symmetry
    assert np.allclose(one_int, one_int.T)
    assert np.allclose(two_int, np.einsum('ijkl->jilk', two_int))
    assert np.allclose(two_int, np.einsum('ijkl->klij', two_int))

    test_ham = RestrictedChemicalHamiltonian(one_int, two_int)
    epsilon = 1e-8
    sds = sd_list(3, 4, num_limit=None, exc_orders=None)

    for sd1 in sds:
        for sd2 in sds:
            for i in range(test_ham.nparams):
                addition = np.zeros(test_ham.nparams)
                addition[i] = epsilon
                test_ham2 = RestrictedChemicalHamiltonian(one_int, two_int, params=addition)

                finite_diff = (np.array(test_ham2.integrate_sd_sd(sd1, sd2))
                               - np.array(test_ham.integrate_sd_sd(sd1, sd2))) / epsilon
                derivative = test_ham._integrate_sd_sd_deriv(sd1, sd2, i)
                assert np.allclose(finite_diff, derivative, atol=20*epsilon)


def test_integrate_sd_sd_deriv_fdiff_random_small():
    """Test GeneralizedChemicalHamiltonian._integrate_sd_sd_deriv using random 1e system.

    Computed derivatives are compared against finite difference of the `integrate_sd_sd`.

    """
    one_int = np.random.rand(2, 2)
    one_int = one_int + one_int.T
    two_int = np.random.rand(2, 2, 2, 2)
    two_int = np.einsum('ijkl->jilk', two_int) + two_int
    two_int = np.einsum('ijkl->klij', two_int) + two_int

    # check that the integrals have the appropriate symmetry
    assert np.allclose(one_int, one_int.T)
    assert np.allclose(two_int, np.einsum('ijkl->jilk', two_int))
    assert np.allclose(two_int, np.einsum('ijkl->klij', two_int))

    test_ham = RestrictedChemicalHamiltonian(one_int, two_int)
    epsilon = 1e-8
    sds = sd_list(1, 2, num_limit=None, exc_orders=None)

    for sd1 in sds:
        for sd2 in sds:
            for i in range(test_ham.nparams):
                addition = np.zeros(test_ham.nparams)
                addition[i] = epsilon
                test_ham2 = RestrictedChemicalHamiltonian(one_int, two_int, params=addition)

                finite_diff = (np.array(test_ham2.integrate_sd_sd(sd1, sd2))
                               - np.array(test_ham.integrate_sd_sd(sd1, sd2))) / epsilon
                derivative = test_ham._integrate_sd_sd_deriv(sd1, sd2, i)
                assert np.allclose(finite_diff, derivative, atol=20*epsilon)
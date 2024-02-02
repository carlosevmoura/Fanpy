"""Script for utilizing PySCF.

Functions
---------
hartreefock(xyz_file, basis, is_unrestricted=False)
    Runs HF in PySCF and generates the corresponding one- and two-electron integrals.

"""
# pylint: disable=C0103,E0611
import ctypes
import os
import re

from fanpy.tools.math_tools import power_symmetric

import numpy as np
import scipy.linalg

from pyscf import ao2mo, gto, lo, scf, __config__
from pyscf.fci import cistring
from pyscf.lib import hermi_triu, load_library
from pyscf.tools import molden
from pyscf.lo.iao import reference_mol


LIBFCI = load_library("libfci")


def hartreefock(xyz_file, basis, is_unrestricted=False):
    """Run HF using PySCF.

    Parameters
    ----------
    xyz_file : str
        XYZ file location.
        Units are in Angstrom.
    basis : str
        Basis set available in PySCF.
    is_unrestricted : bool
        Flag to run unrestricted HF.
        Default is restricted HF.

    Returns
    -------
    result : dict
        "hf_energy"
            The electronic energy.
        "nuc_nuc"
            The nuclear repulsion energy.
        "one_int"
            The tuple of the one-electron interal.
        "two_int"
            The tuple of the two-electron integral in Physicist's notation.

    Raises
    ------
    ValueError
        If given xyz file does not exist.
    NotImplementedError
        If calculation is unrestricted or generalized.

    """
    # check xyz file
    cwd = os.path.dirname(__file__)
    if os.path.isfile(os.path.join(cwd, xyz_file)):
        xyz_file = os.path.join(cwd, xyz_file)
    elif not os.path.isfile(xyz_file):  # pragma: no branch
        raise ValueError("Given xyz_file does not exist")

    # get coordinates
    with open(xyz_file, "r") as f:
        lines = [i.strip() for i in f.readlines()[2:]]
        atoms = ";".join(lines)

    # get mol
    mol = gto.M(atom=atoms, basis=basis, parse_arg=False, unit="angstrom")

    # get hf
    if is_unrestricted:
        raise NotImplementedError(
            "Unrestricted or Generalized orbitals are not supported in this" " PySCF wrapper (yet)."
        )
    hf = scf.RHF(mol)
    # run hf
    hf.scf()
    # energies
    energy_nuc = hf.energy_nuc()
    energy_tot = hf.kernel()  # HF is solved here
    energy_elec = energy_tot - energy_nuc
    # mo_coeffs
    mo_coeff = hf.mo_coeff
    # Get integrals (See pyscf.gto.moleintor.getints_by_shell for other types of integrals)
    # get 1e integral
    one_int_ab = mol.intor("cint1e_nuc_sph") + mol.intor("cint1e_kin_sph")
    one_int = mo_coeff.T.dot(one_int_ab).dot(mo_coeff)
    # get 2e integral
    eri = ao2mo.full(mol, mo_coeff, verbose=0, intor="cint2e_sph")
    two_int = ao2mo.restore(1, eri, mol.nao_nr())
    # NOTE: PySCF uses Chemist's notation
    two_int = np.einsum("ijkl->ikjl", two_int)
    # results
    result = {
        "hf_energy": energy_elec,
        "nuc_nuc": energy_nuc,
        "one_int": one_int,
        "two_int": two_int,
    }
    return result


def fci_cimatrix(h1e, eri, nelec, is_chemist_notation=False):
    """Construct the FCI CI Hamiltonian matrix using PySCF.

    Parameters
    ----------
    h1e : np.ndarray(K, K)
        One electron integrals.
    eri : np.ndarray(K, K, K, K)
        Two electron integrals.
    nelec : int
        Number of electrons.
    is_chemist_notation : bool
        Flag to set the notation for the two electron integrals.
        By default, it is assumed that the Physicist's notation is used for the two electron
        integrals.

    Returns
    -------
    ci_matrix : np.ndarray(M, M)
        CI Hamiltonian matrix.
    pspace : list(M)
        List of the Slater determinants (in bitstring) that corresponds to each row/column of the
        `ci_matrix`.

    Raises
    ------
    ValueError
        If number of electrons is invalid.

    """
    if not is_chemist_notation:
        eri = np.einsum("ijkl->ikjl", eri)
    # adapted/copied from pyscf.fci.direct_spin1.make_hdiag
    # number of spatial orbitals
    norb = h1e.shape[0]
    # number of electrons
    if isinstance(nelec, (int, np.number)):
        # beta
        nelecb = nelec // 2
        # alpha
        neleca = nelec - nelecb
    elif isinstance(nelec, (tuple, list)) and len(nelec) == 2:
        neleca, nelecb = nelec
    else:
        raise ValueError("Unsupported electron number, {0}".format(nelec))
    # integrals
    h1e = np.asarray(h1e, order="C")
    eri = np.asarray(eri, order="C")
    # Construct some sort of lookup table to link different bit string occupations
    # to one another. i.e. From one bit string, and several indices that describes
    # certain excitation, we can get the other bit string
    # NOTE: PySCF treats alpha and the beta bits separately
    occslista = np.asarray(cistring._gen_occslst(range(norb), neleca))  # pylint: disable=W0212
    occslistb = np.asarray(cistring._gen_occslst(range(norb), nelecb))  # pylint: disable=W0212
    # number of Slater determinants
    na = len(occslista)  # number of "alpha" Slater determinants
    nb = len(occslistb)  # number of "beta" Slater determinants
    num_sd = na * nb  # number of Slater determinants in total

    # Diagonal of CI Hamiltonian matrix
    hdiag = np.empty(num_sd)
    # Coulomb integrals
    jdiag = np.asarray(np.einsum("iijj->ij", eri), order="C")
    # Exchange integrals
    kdiag = np.asarray(np.einsum("ijji->ij", eri), order="C")
    # Fucking Magic
    LIBFCI.FCImake_hdiag_uhf(
        hdiag.ctypes.data_as(ctypes.c_void_p),
        h1e.ctypes.data_as(ctypes.c_void_p),
        h1e.ctypes.data_as(ctypes.c_void_p),
        jdiag.ctypes.data_as(ctypes.c_void_p),
        jdiag.ctypes.data_as(ctypes.c_void_p),
        jdiag.ctypes.data_as(ctypes.c_void_p),
        kdiag.ctypes.data_as(ctypes.c_void_p),
        kdiag.ctypes.data_as(ctypes.c_void_p),
        ctypes.c_int(norb),
        ctypes.c_int(na),
        ctypes.c_int(nb),
        ctypes.c_int(neleca),
        ctypes.c_int(nelecb),
        occslista.ctypes.data_as(ctypes.c_void_p),
        occslistb.ctypes.data_as(ctypes.c_void_p),
    )

    # adapted/copied from pyscf.fci.direct_spin1.pspace
    # PySCF has a fancy indicing of Slater determinants (bitstrings to consecutive integers)
    addr = np.arange(hdiag.size)
    # again, separate the alpha and the beta parts
    addra, addrb = divmod(addr, nb)
    # bit strings for the alpha and beta parts
    stra = cistring.addrs2str(norb, neleca, addra)
    strb = cistring.addrs2str(norb, nelecb, addrb)
    # number of slater determinants
    ci_matrix = np.zeros((num_sd, num_sd))
    # More Fucking Magic
    LIBFCI.FCIpspace_h0tril(
        ci_matrix.ctypes.data_as(ctypes.c_void_p),
        h1e.ctypes.data_as(ctypes.c_void_p),
        eri.ctypes.data_as(ctypes.c_void_p),
        stra.ctypes.data_as(ctypes.c_void_p),
        strb.ctypes.data_as(ctypes.c_void_p),
        ctypes.c_int(norb),
        ctypes.c_int(num_sd),
    )

    for i in range(num_sd):
        ci_matrix[i, i] = hdiag[addr[i]]
    ci_matrix = hermi_triu(ci_matrix)

    # convert  PySCF Slater determinant notation to one that we use
    pspace = []
    for i in addr:
        # beta b/c the modulus corresponds to the "beta slater determinant" index
        addra, addrb = divmod(i, nb)
        alpha_bit = cistring.addr2str(norb, neleca, addra)
        beta_bit = cistring.addr2str(norb, nelecb, addrb)
        # hard code in slater.combine_spin
        pspace.append(alpha_bit | (beta_bit << norb))

    return ci_matrix, pspace


def convert_gbs_nwchem(gbs_file: str):
    """Convert gbs file to nwchem.

    Parameters
    ----------
    gbs_file : str
        Name of the gbs file.

    Returns
    -------
    gbs_dict : dict

    """
    gbs_dict = {}
    with open(gbs_file, 'r') as f:
        all_lines = f.read()
    sections = all_lines.split('****')
    # first section is the comments
    for section in sections[1:]:
        section = section.strip()
        if not section:
            continue
        atom, *orb_coeffs = re.split(r"\s*(\w+)\s+\d+\s+\d+\.\d+\n", section)
        # find atom
        atom = re.search(r"^(\w+)\s", atom).group(1)
        # assign dict
        for orbtype, coeffs in zip(orb_coeffs[::2], orb_coeffs[1::2]):
            coeffs = coeffs.rstrip()
            if atom in gbs_dict:
                gbs_dict[atom] = gbs_dict[atom] + f'{atom} {orbtype}\n{coeffs}\n'
            else:
                gbs_dict[atom] = f'{atom} {orbtype}\n{coeffs}\n'
    return gbs_dict


def localize(xyz_file, basis_file, mo_coeff_file=None, unit='Bohr', method=None, system_inds=None):
    """Run HF using PySCF.

    Parameters
    ----------
    xyz_file : str
        XYZ file location.
    basis_file : str
        Basis file location
    is_unrestricted : bool
        Flag to run unrestricted HF.
        Default is restricted HF.

    Returns
    -------
    result : dict
        "hf_energy"
            The electronic energy.
        "nuc_nuc"
            The nuclear repulsion energy.
        "one_int"
            The tuple of the one-electron interal.
        "two_int"
            The tuple of the two-electron integral in Physicist's notation.

    Raises
    ------
    ValueError
        If given xyz file does not exist.
    NotImplementedError
        If calculation is unrestricted or generalized.

    """
    # check xyz file
    cwd = os.path.dirname(__file__)
    if os.path.isfile(os.path.join(cwd, xyz_file)):
        xyz_file = os.path.join(cwd, xyz_file)
    elif not os.path.isfile(xyz_file):  # pragma: no branch
        raise ValueError("Given xyz_file does not exist")

    # get coordinates
    with open(xyz_file, "r") as f:
        lines = [i.strip() for i in f.readlines()[2:]]
        #if unit in ["bohr", "Bohr"]:
        #    lines = [" ".join([str(float(j) * 0.529177249) if i != 0 else j for i, j in enumerate(line.split())]) for line in lines]
        atoms = ";".join(lines)
    

    # get mol
    if os.path.splitext(basis_file)[1] == ".gbs":
        basis = convert_gbs_nwchem(basis_file)
    else:
        basis = basis_file
    mol = gto.M(
        atom=atoms, basis={i: j for i, j in basis.items() if i + ' ' in atoms}, parse_arg=False,
        unit=unit
    )

    # get hf
    hf = scf.RHF(mol)
    # run hf
    hf.scf()

    # energies
    energy_nuc = hf.energy_nuc()
    energy_tot = hf.kernel()  # HF is solved here
    energy_elec = energy_tot - energy_nuc

    # mo_coeffs
    if mo_coeff_file is None:
        mo_coeff = hf.mo_coeff
    else:
        mo_coeff = np.load(mo_coeff_file)

    # Get integrals (See pyscf.gto.moleintor.getints_by_shell for other types of integrals)
    # get 1e integral
    one_int_ab = mol.intor("cint1e_nuc_sph") + mol.intor("cint1e_kin_sph")
    one_int = mo_coeff.T.dot(one_int_ab).dot(mo_coeff)
    # get 2e integral
    eri = ao2mo.full(mol, mo_coeff, verbose=0, intor="cint2e_sph")
    two_int = ao2mo.restore(1, eri, mol.nao_nr())
    # FIXME: pyscf integrals
    hcore_ao = mol.intor_symmetric('int1e_kin') + mol.intor_symmetric('int1e_nuc')
    one_int = np.einsum('pi,pq,qj->ij', mo_coeff, hcore_ao, mo_coeff)
    eri_4fold_ao = mol.intor('int2e_sph', aosym=1)
    two_int = ao2mo.incore.full(eri_4fold_ao, mo_coeff)

    # NOTE: PySCF uses Chemist's notation
    two_int = np.einsum("ijkl->ikjl", two_int)

    # labels
    ao_labels = mol.ao_labels()
    ao_inds = [int(re.search(r'^(\d+)\s+', label).group(1)) for label in ao_labels]

    # results
    result = {
        "hf_energy": energy_elec,
        "nuc_nuc": energy_nuc,
        "one_int": one_int,
        "two_int": two_int,
        "t_ab_mo": mo_coeff,
        "ao_inds": ao_inds,
    }

    if method is None:
        return result

    # energy check
    one_energy = np.einsum('ii->i', one_int)
    two_energy = 2 * np.einsum('ijij->ij', two_int)
    two_energy -= np.einsum('ijji->ij', two_int)
    two_energy = np.sum(two_energy[:, :hf.mol.nelectron // 2], axis=1)
    print("pyscf mo energies:", hf.mo_energy)
    print("computed mo energies:", one_energy + two_energy)
    print("pyscf hf electronic energy:", energy_elec)
    print("computed hf electronic energy:", 2 * np.sum(one_energy[:hf.mol.nelectron // 2]) + np.sum(two_energy[:hf.mol.nelectron // 2]))

    if method != "svd":
        if method == "iao":
            t_ab_lo= lo.iao.iao(mol, mo_coeff[:,hf.mo_occ > 0], minao="sto-6g")
            # Orthogonalize IAO
            t_ab_lo = lo.vec_lowdin(t_ab_lo, hf.get_ovlp())
        elif method == "boys":
            t_ab_lo = lo.Boys(hf.mol, mo_coeff).kernel()
        elif method == "pm":
            t_ab_lo = lo.PM(hf.mol, mo_coeff).kernel()
        elif method == "er":
            t_ab_lo = lo.ER(hf.mol, mo_coeff).kernel()
        else:
            t_ab_lo = np.identity(mo_coeff.shape[0])

        olp_ab_ab = mol.intor_symmetric('int1e_ovlp')

        # find the localized orbitals that contribute the most to occupied mo
        olp_omo_lo = mo_coeff[:, hf.mo_occ > 0].T.dot(olp_ab_ab).dot(t_ab_lo)
        indices_lo = np.argsort(np.diag(olp_omo_lo.T.dot(olp_omo_lo)))[::-1]
        # orbitals that are best spanned by occupied orbitals will be considered "occupied"
        indices_occ_lo, indices_vir_lo = indices_lo[:hf.mol.nelectron // 2], indices_lo[hf.mol.nelectron // 2:]
        #print(np.diag(olp_omo_lo.T.dot(olp_omo_lo)))
        #print(indices_occ_lo)
        #print(indices_vir_lo)

        # find closest unitary matrix
        u, _, vh = np.linalg.svd(olp_omo_lo[:, indices_occ_lo])
        t_omo_olo = u.dot(vh)
        assert np.allclose(t_omo_olo.T.dot(t_omo_olo), np.identity(t_omo_olo.shape[1]))
        assert np.allclose(t_omo_olo.dot(t_omo_olo.T), np.identity(t_omo_olo.shape[1]))
        #t_mo_lo[np.where(hf.mo_occ > 0)[0][:, None], indices_occ_ab[None, :]] = u.dot(vh)

        # find the localized orbitals that contribute the most to virtual mo
        olp_vmo_lo = mo_coeff[:, hf.mo_occ == 0].T.dot(olp_ab_ab).dot(t_ab_lo)
        u, _, vh = np.linalg.svd(olp_vmo_lo[:, indices_vir_lo])
        t_vmo_vlo = u.dot(vh)
        #t_mo_lo[np.where(hf.mo_occ == 0)[0][:, None], indices_vir_ab[None, :]] = u.dot(vh)
        assert np.allclose(t_vmo_vlo.T.dot(t_vmo_vlo), np.identity(t_vmo_vlo.shape[1]))
        assert np.allclose(t_vmo_vlo.dot(t_vmo_vlo.T), np.identity(t_vmo_vlo.shape[1]))

        # make transformation matrix from mo
        t_mo_lo = scipy.linalg.block_diag(t_omo_olo, t_vmo_vlo)
        assert np.allclose(t_mo_lo.T.dot(t_mo_lo), np.identity(t_mo_lo.shape[1]))
        assert np.allclose(t_mo_lo.dot(t_mo_lo.T), np.identity(t_mo_lo.shape[1]))

        # make transformation matrix from ab
        t_ab_lo = mo_coeff.dot(t_mo_lo)

        # FIXME: check
        # assign lo to atom/system
        new_lo_inds = []
        # I AM ASSUMING THAT LO'S CORRESPOND TO AO'S
        olp_lo_ab = t_ab_lo.T.dot(olp_ab_ab)

        #np.set_printoptions(precision=3)
        #print(olp_lo_ab) #for i in indices_occ_lo.tolist() + indices_vir_lo.tolist():
        for i in range(indices_occ_lo.size + indices_vir_lo.size):
            ao_ind = np.argmax(np.abs(olp_lo_ab[i]))
            #print(i, ao_ind, ao_inds[ao_ind])
            new_lo_inds.append(ao_inds[ao_ind])
        #print(ao_inds)
        result["ao_inds"] = new_lo_inds
        result["nelecs"] = [np.sum(indices_occ_lo == i ) for i in range(max(system_inds) + 1)]

        #print(t_ab_lo)
    else:
        MINAO = getattr(__config__, 'lo_iao_minao', 'minao')

        pmol = reference_mol(mol, MINAO)
        orig_s12 = gto.mole.intor_cross('int1e_ovlp', mol, pmol)

        minao_labels = pmol.ao_labels()
        minao_inds = np.array([system_inds[int(re.search(r'^(\d+)\s+', label).group(1))] for label in minao_labels])
        #print(minao_labels)
        #print(minao_inds)

        coeff_mo_lo = []
        new_lo_inds = []
        for sub_mo_coeff in [mo_coeff[:, hf.mo_occ > 0], mo_coeff[:, hf.mo_occ == 0]]:
            s12 = sub_mo_coeff.T.dot(orig_s12)
            system_s12 = []
            for i in range(max(system_inds) + 1):
                system_s12.append(s12[:, minao_inds == i])

            system_mo_lo_T = [[] for i in range(max(system_inds) + 1)]
            counter = 0
            cum_transform = np.identity(s12.shape[0])
            while counter < sub_mo_coeff.shape[1]:
                system_u = []
                system_s = []
                for s12 in system_s12:
                    u, s, vdag = np.linalg.svd(s12)
                    system_u.append(u.T)
                    system_s.append(s)
                    # TEST: negative singular value?
                    assert np.all(s > 0)
                    #print(s12)
                    #print(s)
                # find which system had the largest singular value
                max_system_ind = np.argmax([max(s) for s in system_s])
                # find largest singular value
                max_sigma_ind = np.argmax(system_s[max_system_ind])
                # add corresponding left singular vector
                system_mo_lo_T[max_system_ind].append(system_u[max_system_ind][max_sigma_ind].dot(cum_transform))
                # update overlap matrix (remove singular vector)
                trunc_transform = np.delete(system_u[max_system_ind], max_sigma_ind, axis=0)
                assert np.allclose(trunc_transform.dot(trunc_transform.T), np.identity(trunc_transform.shape[0]))
                for i in range(len(system_s12)):
                    system_s12[i] = trunc_transform.dot(system_s12[i])
                # update transformation matrix
                cum_transform = trunc_transform.dot(cum_transform)
                # increment
                counter += 1

            lo_inds = [[i] * len(rows) for i, rows in enumerate(system_mo_lo_T)]
            lo_inds = [j for i in lo_inds for j in i]
            new_lo_inds.append(lo_inds)
            lo_inds = np.array(lo_inds)
            #print(lo_inds, 'y'*99)

            system_mo_lo_T = np.vstack([np.vstack(rows) for rows in system_mo_lo_T if rows])
            #np.set_printoptions(linewidth=200)
            #print(system_mo_lo_T)

            # check orthogonalization
            s1 = mol.intor_symmetric('int1e_ovlp')
            transform = system_mo_lo_T.dot(sub_mo_coeff.T)
            olp = transform.dot(s1).dot(transform.T)
            #print(olp)
            assert np.allclose(olp, np.identity(transform.shape[0]))

            # check span
            s12 = gto.mole.intor_cross('int1e_ovlp', mol, pmol)
            s12 = sub_mo_coeff.T.dot(s12)
            s12 = system_mo_lo_T.dot(s12)
            for i in range(max(system_inds) + 1):
                # how much is inside
                system_s12 = s12[lo_inds == i][:, minao_inds == i]
                #print(np.sum(np.diag(system_s12.T.dot(system_s12))))
                # how much is outside
                system_s12 = s12[lo_inds == i][:, minao_inds != i]
                #print(np.sum(np.diag(system_s12.T.dot(system_s12))))

            assert np.allclose(system_mo_lo_T.dot(system_mo_lo_T.T), np.identity(system_mo_lo_T.shape[0]))
            coeff_mo_lo.append(system_mo_lo_T.T)

        # visualize
        #temp = np.zeros((coeff_mo_lo[0].shape[0] + coeff_mo_lo[1].shape[0], coeff_mo_lo[0].shape[1] + coeff_mo_lo[1].shape[1]))
        #temp[np.where(hf.mo_occ > 0)[0][:, None],  np.where(np.arange(temp.shape[1]) < nelec // 2)[0][None, :]] = coeff_mo_lo[0] 
        #temp[np.where(hf.mo_occ == 0)[0][:, None], np.where(np.arange(temp.shape[1]) >= nelec // 2)[0][None, :]] = coeff_mo_lo[1] 
        coeff_mo_lo = scipy.linalg.block_diag(*coeff_mo_lo)
        #assert np.allclose(coeff_mo_lo, temp)
        t_ab_lo = mo_coeff.dot(coeff_mo_lo)

        result["ao_inds"] = [j for i in new_lo_inds for j in i]
        indices_occ_lo = np.array(new_lo_inds[0])
        result["nelecs"] = [np.sum(indices_occ_lo == i ) for i in range(max(system_inds) + 1)]

    t_mo_lo = np.linalg.solve(mo_coeff, t_ab_lo)
    t_lo_mo = np.linalg.solve(t_ab_lo, mo_coeff)
    assert np.allclose(mo_coeff, t_ab_lo.dot(t_lo_mo))
    # check orthogonal
    assert np.allclose(t_mo_lo.T.dot(t_mo_lo), np.identity(t_mo_lo.shape[1]))

    #t_mo_lo[np.abs(t_mo_lo) < 1e-7] = 0
    #t_lo_mo[np.abs(t_lo_mo) < 1e-7] = 0
    assert np.allclose(t_ab_lo, mo_coeff.dot(t_mo_lo))
    assert np.allclose(t_mo_lo.T.dot(t_mo_lo), np.identity(t_mo_lo.shape[1]))

    molden.from_mo(mol, f'{method}.molden', t_ab_lo)
    molden.from_mo(mol, 'mo.molden', mo_coeff)

    one_int = t_mo_lo.T.dot(one_int).dot(t_mo_lo)
    two_int = np.einsum('ijkl,ia->ajkl', two_int, t_mo_lo)
    two_int = np.einsum('ajkl,jb->abkl', two_int, t_mo_lo)
    two_int = np.einsum('abkl,kc->abcl', two_int, t_mo_lo)
    two_int = np.einsum('abcl,ld->abcd', two_int, t_mo_lo)

    result['one_int'] = one_int
    result['two_int'] = two_int
    result['t_ab_mo'] = t_ab_lo
    return result

""" reaction finders

Function arguments:
    Each function takes a list of reactant graphs and a list of product graphs.
    Note that the reactant graphs *cannot* have overlapping atom keys, and
    likewise for the product graphs. Otherwise, there would be no way to
    express the bonds broken and formed between reactants.
"""

import itertools
import automol.geom
import automol.geom.ts
import automol.inchi
from automol.par import ReactionClass
from automol.graph import ts
from automol.graph import atom_keys
from automol.graph import bond_keys
from automol.graph import formula
from automol.graph import union
from automol.graph import add_bonds
from automol.graph import remove_bonds
from automol.graph import isomorphism
from automol.graph import equivalent_atoms
from automol.graph import union_from_sequence
from automol.graph import unsaturated_atom_keys
from automol.graph import atom_neighbor_atom_key
from automol.graph import atoms_neighbor_atom_keys
from automol.graph import add_bonded_atom
from automol.graph import add_atom_explicit_hydrogen_keys
from automol.graph import rings_bond_keys
from automol.graph import rings_atom_keys
from automol.reac._reac import Reaction
from automol.reac._reac import reverse
from automol.reac._reac import ts_unique
from automol.reac._util import assert_is_valid_reagent_graph_list
from automol.reac._util import sort_reagents


def trivial(rct_gras, prd_gras):
    """ find a trivial reaction, with the same reactants and products
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == len(prd_gras):
        rct_idxs = []
        prd_idxs = []

        # One at a time, find matches for each reactant; track the positions to
        # get the right sort order
        prd_gras_pool = list(prd_gras)
        for rct_idx, rct_gra in enumerate(rct_gras):
            prd_idx = next((idx for idx, prd_gra in enumerate(prd_gras_pool)
                            if isomorphism(rct_gra, prd_gra)), None)

            if prd_idx is not None:
                rct_idxs.append(rct_idx)
                prd_idxs.append(prd_idx)
                prd_gras_pool.pop(prd_idx)
            else:
                break

        if rct_idxs and prd_idxs:
            # reorder the reactants and products
            rct_gras = list(map(rct_gras.__getitem__, rct_idxs))
            prd_gras = list(map(prd_gras.__getitem__, prd_idxs))

            rcts_gra = union_from_sequence(rct_gras)
            prds_gra = union_from_sequence(prd_gras)

            rxns.append(Reaction(
                rxn_cls=ReactionClass.Typ.TRIVIAL,
                forw_tsg=ts.graph(rcts_gra, [], []),
                back_tsg=ts.graph(prds_gra, [], []),
                rcts_keys=list(map(atom_keys, rct_gras)),
                prds_keys=list(map(atom_keys, prd_gras)),
            ))

    return tuple(rxns)


# Unimolecular reactions
# 1. Hydrogen migrations
def hydrogen_migrations(rct_gras, prd_gras):
    """ find hydrogen migrations consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Hydrogen migrations are identified by adding a hydrogen to an unsaturated
    site of the reactant and adding a hydrogen to an unsaturated site of the
    product and seeing if they match up. If so, we have a hydrogen migration
    between these two sites.
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == 1 and len(prd_gras) == 1:
        rct_gra, = rct_gras
        prd_gra, = prd_gras

        # Find keys for reactant graph
        rct_h_key = max(atom_keys(rct_gra)) + 1
        rct_rad_keys = unsaturated_atom_keys(rct_gra)

        # Find keys for product graph
        prd_h_key = max(atom_keys(prd_gra)) + 1
        prd_rad_keys = unsaturated_atom_keys(prd_gra)

        for rct_rad_key, prd_rad_key in (
                itertools.product(rct_rad_keys, prd_rad_keys)):
            # Add hydrogens to each radical site and see if the result matches
            rct_h_gra = add_bonded_atom(
                rct_gra, 'H', rct_rad_key, bnd_atm_key=rct_h_key)
            prd_h_gra = add_bonded_atom(
                prd_gra, 'H', prd_rad_key, bnd_atm_key=prd_h_key)

            iso_dct = isomorphism(rct_h_gra, prd_h_gra)
            if iso_dct:
                inv_dct = dict(map(reversed, iso_dct.items()))

                rct_don_key = inv_dct[prd_rad_key]
                prd_don_key = iso_dct[rct_rad_key]

                # Check equivalent donor atoms for other possible TSs
                rct_don_keys = equivalent_atoms(rct_h_gra, rct_don_key)
                prd_don_keys = equivalent_atoms(prd_h_gra, prd_don_key)

                for rct_don_key, prd_don_key in (
                        itertools.product(rct_don_keys, prd_don_keys)):
                    rct_hyd_key = atom_neighbor_atom_key(
                        rct_gra, rct_don_key, symbs_first=('H',),
                        symbs_last=())
                    prd_hyd_key = atom_neighbor_atom_key(
                        prd_gra, prd_don_key, symbs_first=('H',),
                        symbs_last=())

                    forw_tsg = ts.graph(
                        rct_gra,
                        frm_bnd_keys=[(rct_rad_key, rct_hyd_key)],
                        brk_bnd_keys=[(rct_don_key, rct_hyd_key)])

                    back_tsg = ts.graph(
                        prd_gra,
                        frm_bnd_keys=[(prd_rad_key, prd_hyd_key)],
                        brk_bnd_keys=[(prd_don_key, prd_hyd_key)])

                    if isomorphism(forw_tsg, ts.reverse(back_tsg)):
                        rxns.append(Reaction(
                            rxn_cls=ReactionClass.Typ.HYDROGEN_MIGRATION,
                            forw_tsg=forw_tsg,
                            back_tsg=back_tsg,
                            rcts_keys=[atom_keys(rct_gra)],
                            prds_keys=[atom_keys(prd_gra)],
                        ))

    return ts_unique(rxns)


# 2. Beta scissions
def beta_scissions(rct_gras, prd_gras):
    """ find beta scission reactions

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Implemented as the reverse of additions.
    """
    rxns = tuple(map(reverse, additions(prd_gras, rct_gras)))
    return rxns


# 3. Ring-forming scissions
def ring_forming_scissions(rct_gras, prd_gras):
    """ find ring-forming scissions consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Ring-forming scissions are found by breaking ring-bonds on one product and
    joining the ends to unsaturated sites on the other product
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == 1 and len(prd_gras) == 2:
        rgra, = rct_gras
        pgra = union_from_sequence(prd_gras)
        for pgra1, pgra2 in itertools.permutations(prd_gras):
            bnd_keys = list(itertools.chain(*rings_bond_keys(pgra1)))
            atm_keys = unsaturated_atom_keys(pgra2)

            for bnd_key, atm_key in itertools.product(bnd_keys, atm_keys):
                # Break a ring bond
                gra = remove_bonds(pgra, [bnd_key])

                for end_key in bnd_key:
                    # Add to one end of the broken ring
                    fgra = add_bonds(gra, [(atm_key, end_key)])
                    inv_dct = isomorphism(fgra, rgra)
                    if inv_dct:
                        other_end_key, = bnd_key - {end_key}
                        f_frm_bnd_key = (inv_dct[end_key],
                                         inv_dct[other_end_key])
                        f_brk_bnd_key = (inv_dct[end_key], inv_dct[atm_key])
                        b_frm_bnd_key = (end_key, atm_key)
                        b_brk_bnd_key = (end_key, other_end_key)
                        forw_tsg = ts.graph(rgra,
                                            frm_bnd_keys=[f_frm_bnd_key],
                                            brk_bnd_keys=[f_brk_bnd_key])
                        back_tsg = ts.graph(pgra,
                                            frm_bnd_keys=[b_frm_bnd_key],
                                            brk_bnd_keys=[b_brk_bnd_key])

                        # Create the reaction object
                        rxns.append(Reaction(
                            rxn_cls=ReactionClass.Typ.RING_FORM_SCISSION,
                            forw_tsg=forw_tsg,
                            back_tsg=back_tsg,
                            rcts_keys=[atom_keys(rgra)],
                            prds_keys=[atom_keys(pgra1), atom_keys(pgra2)],
                        ))

    return ts_unique(rxns)


# 4. Eliminations
def eliminations(rct_gras, prd_gras):
    """ find eliminations consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Eliminations are identified by forming a bond between an attacking heavy
    atom and another atom not initially bonded to it, forming a ring. The bond
    adjacent to the attacked atom is then broken, along with a second bond in
    the ring, downstream of the attacking heavy atom, away from the attacked
    atom.
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == 1 and len(prd_gras) == 2:
        rct_gra, = rct_gras
        prds_gra = union_from_sequence(prd_gras)

        ngb_keys_dct = atoms_neighbor_atom_keys(rct_gra)

        frm1_keys = atom_keys(rct_gra, excl_syms=('H',))
        frm2_keys = atom_keys(rct_gra)
        bnd_keys = bond_keys(rct_gra)

        frm_bnd_keys = [(frm1_key, frm2_key) for frm1_key, frm2_key
                        in itertools.product(frm1_keys, frm2_keys)
                        if frm1_key != frm2_key and
                        not frozenset({frm1_key, frm2_key}) in bnd_keys]

        for frm1_key, frm2_key in frm_bnd_keys:
            # Bond the radical atom to the hydrogen atom
            prds_gra_ = add_bonds(rct_gra, [(frm2_key, frm1_key)])

            # Get keys to the ring formed by this extra bond
            rng_keys = next((ks for ks in rings_atom_keys(prds_gra_)
                             if frm2_key in ks and frm1_key in ks), None)

            # Eliminations (as far as I can tell) only happen through TSs with
            # 3- or 4-membered rings
            if rng_keys is not None and len(rng_keys) < 5:
                frm1_ngb_key, = ngb_keys_dct[frm1_key] & set(rng_keys)
                frm2_ngb_key, = ngb_keys_dct[frm2_key] & set(rng_keys)

                # Break the bonds on either side of the newly formed bond
                prds_gra_ = remove_bonds(prds_gra_, [(frm1_key, frm1_ngb_key)])
                prds_gra_ = remove_bonds(prds_gra_, [(frm2_key, frm2_ngb_key)])

                inv_dct = isomorphism(prds_gra_, prds_gra)
                if inv_dct:
                    f_frm_bnd_key = (frm1_key, frm2_key)
                    f_brk_bnd_key1 = (frm1_key, frm1_ngb_key)
                    f_brk_bnd_key2 = (frm2_key, frm2_ngb_key)
                    inv_ = inv_dct.__getitem__
                    b_frm_bnd_key1 = tuple(map(inv_, f_brk_bnd_key1))
                    b_frm_bnd_key2 = tuple(map(inv_, f_brk_bnd_key2))
                    b_brk_bnd_key = tuple(map(inv_, f_frm_bnd_key))

                    forw_tsg = ts.graph(rct_gra,
                                        frm_bnd_keys=[f_frm_bnd_key],
                                        brk_bnd_keys=[f_brk_bnd_key1,
                                                      f_brk_bnd_key2])
                    back_tsg = ts.graph(prds_gra,
                                        frm_bnd_keys=[b_frm_bnd_key1,
                                                      b_frm_bnd_key2],
                                        brk_bnd_keys=[b_brk_bnd_key])

                    rcts_atm_keys = list(map(atom_keys, rct_gras))
                    prds_atm_keys = list(map(atom_keys, prd_gras))

                    if inv_dct[frm1_key] not in prds_atm_keys[1]:
                        prds_atm_keys = list(reversed(prds_atm_keys))

                    assert inv_dct[frm1_key] in prds_atm_keys[1]
                    assert inv_dct[frm2_key] in prds_atm_keys[1]

                    # Create the reaction object
                    rxns.append(Reaction(
                        rxn_cls=ReactionClass.Typ.ELIMINATION,
                        forw_tsg=forw_tsg,
                        back_tsg=back_tsg,
                        rcts_keys=rcts_atm_keys,
                        prds_keys=prds_atm_keys,
                    ))

    return ts_unique(rxns)


# Bimolecular reactions
# 1. Hydrogen abstractions
def hydrogen_abstractions(rct_gras, prd_gras):
    """ find hydrogen abstractions consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Hydrogen abstractions are identified first by checking whether the
    molecular formulas are consistent with a reaction of the form R1H + R2 =>
    R2H + R1. If they do, we identify the abstraction sites by adding hydrogens
    to unsaturated sites of the R1 product to see if we get the R1H reactant.
    We then do the same for the R2 reactant and the R2H product.
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == 2 and len(prd_gras) == 2:
        rct_fmls = list(map(formula, rct_gras))
        prd_fmls = list(map(formula, prd_gras))

        ret = automol.formula.reac.argsort_hydrogen_abstraction(
            rct_fmls, prd_fmls)
        if ret:
            rct_idxs_, prd_idxs_ = ret
            rct_gras = list(map(rct_gras.__getitem__, rct_idxs_))
            prd_gras = list(map(prd_gras.__getitem__, prd_idxs_))

            q1h_gra, q2_gra = rct_gras
            q2h_gra, q1_gra = prd_gras

            rets1 = _partial_hydrogen_abstraction(q1h_gra, q1_gra)
            rets2 = _partial_hydrogen_abstraction(q2h_gra, q2_gra)
            for ret1, ret2 in itertools.product(rets1, rets2):
                f_q1h_q_atm_key, f_q1h_h_atm_key, b_q2_q_atm_key = ret1
                b_q1h_q_atm_key, b_q1h_h_atm_key, f_q2_q_atm_key = ret2

                # Create the forward/backward ts graphs
                rcts_gra = union_from_sequence(rct_gras)
                prds_gra = union_from_sequence(prd_gras)
                f_frm_bnd_key = (f_q2_q_atm_key, f_q1h_h_atm_key)
                f_brk_bnd_key = (f_q1h_q_atm_key, f_q1h_h_atm_key)
                b_frm_bnd_key = (b_q2_q_atm_key, b_q1h_h_atm_key)
                b_brk_bnd_key = (b_q1h_q_atm_key, b_q1h_h_atm_key)
                forw_tsg = ts.graph(rcts_gra,
                                    frm_bnd_keys=[f_frm_bnd_key],
                                    brk_bnd_keys=[f_brk_bnd_key])
                back_tsg = ts.graph(prds_gra,
                                    frm_bnd_keys=[b_frm_bnd_key],
                                    brk_bnd_keys=[b_brk_bnd_key])

                # Create the reaction object
                rxns.append(Reaction(
                    rxn_cls=ReactionClass.Typ.HYDROGEN_ABSTRACTION,
                    forw_tsg=forw_tsg,
                    back_tsg=back_tsg,
                    rcts_keys=list(map(atom_keys, rct_gras)),
                    prds_keys=list(map(atom_keys, prd_gras)),
                ))

    return ts_unique(rxns)


# 2. Additions
def additions(rct_gras, prd_gras):
    """ find additions consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Additions are identified by joining an unsaturated site on one reactant to
    an unsaturated site on the other. If the result matches the products, this
    is an addition reaction.
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == 2 and len(prd_gras) == 1:
        rct_gras = sort_reagents(rct_gras)
        x_gra, y_gra = rct_gras
        prd_gra, = prd_gras
        x_atm_keys = unsaturated_atom_keys(x_gra)
        y_atm_keys = unsaturated_atom_keys(y_gra)

        for x_atm_key, y_atm_key in itertools.product(x_atm_keys, y_atm_keys):
            xy_gra = add_bonds(
                union(x_gra, y_gra), [{x_atm_key, y_atm_key}])

            iso_dct = isomorphism(xy_gra, prd_gra)
            if iso_dct:
                rcts_gra = union_from_sequence(rct_gras)
                prds_gra = prd_gra
                f_frm_bnd_key = (x_atm_key, y_atm_key)
                b_brk_bnd_key = (iso_dct[x_atm_key], iso_dct[y_atm_key])
                forw_tsg = ts.graph(rcts_gra,
                                    frm_bnd_keys=[f_frm_bnd_key],
                                    brk_bnd_keys=[])
                back_tsg = ts.graph(prds_gra,
                                    frm_bnd_keys=[],
                                    brk_bnd_keys=[b_brk_bnd_key])

                # Create the reaction object
                rxns.append(Reaction(
                    rxn_cls=ReactionClass.Typ.ADDITION,
                    forw_tsg=forw_tsg,
                    back_tsg=back_tsg,
                    rcts_keys=list(map(atom_keys, rct_gras)),
                    prds_keys=list(map(atom_keys, prd_gras)),
                ))

    return ts_unique(rxns)


# 3. Insertions
def insertions(rct_gras, prd_gras):
    """ find insertions consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Implemented as the reverse of an addition reaction.
    """
    rxns = tuple(map(reverse, eliminations(prd_gras, rct_gras)))
    return rxns


# 4. Substitutions
def substitutions(rct_gras, prd_gras):
    """ find substitutions consistent with these reactants and products

    :param rct_gras: reactant graphs (must have non-overlapping keys)
    :param prd_gras: product graphs (must have non-overlapping keys)

    Substitutions are identified by breaking one bond in the reactants and one
    bond from the products and checking for isomorphism.
    """
    assert_is_valid_reagent_graph_list(rct_gras)
    assert_is_valid_reagent_graph_list(prd_gras)

    rxns = []

    if len(rct_gras) == 2 and len(prd_gras) == 2:
        rct_gra = union_from_sequence(rct_gras)
        prd_gra = union_from_sequence(prd_gras)

        for rgra1, rgra2 in itertools.permutations(rct_gras):
            bnd_keys = bond_keys(rgra1)
            rad_keys = unsaturated_atom_keys(rgra2)

            for bnd_key, rad_key in itertools.product(bnd_keys, rad_keys):
                gra = remove_bonds(rct_gra, [bnd_key])

                for brk_key1 in bnd_key:
                    gra = add_bonds(gra, [(brk_key1, rad_key)])

                    inv_dct = isomorphism(gra, prd_gra)
                    if inv_dct:
                        brk_key2, = bnd_key - {brk_key1}
                        f_frm_bnd_key = (brk_key1, rad_key)
                        f_brk_bnd_key = (brk_key1, brk_key2)
                        b_frm_bnd_key = (inv_dct[brk_key1], inv_dct[brk_key2])
                        b_brk_bnd_key = (inv_dct[brk_key1], inv_dct[rad_key])

                        forw_tsg = ts.graph(rct_gra,
                                            frm_bnd_keys=[f_frm_bnd_key],
                                            brk_bnd_keys=[f_brk_bnd_key])
                        back_tsg = ts.graph(prd_gra,
                                            frm_bnd_keys=[b_frm_bnd_key],
                                            brk_bnd_keys=[b_brk_bnd_key])

                        rcts_atm_keys = [atom_keys(rgra1), atom_keys(rgra2)]

                        prds_atm_keys = list(map(atom_keys, prd_gras))
                        if inv_dct[rad_key] not in prds_atm_keys[0]:
                            prds_atm_keys = list(reversed(prds_atm_keys))

                        # Create the reaction object
                        rxns.append(Reaction(
                            rxn_cls=ReactionClass.Typ.SUBSTITUTION,
                            forw_tsg=forw_tsg,
                            back_tsg=back_tsg,
                            rcts_keys=rcts_atm_keys,
                            prds_keys=prds_atm_keys,
                        ))

    return ts_unique(rxns)


def find(rct_gras, prd_gras):
    """ find all reactions consistent with these reactants and products

    :param rct_gras: graphs for the reactants, without stereo and without
        overlapping keys
    :param prd_gras: graphs for the products, without stereo and without
        overlapping keys
    :returns: a list of Reaction objects
    :rtype: tuple[Reaction]
    """
    # check whether this is a valid reaction
    rct_fmls = list(map(formula, rct_gras))
    prd_fmls = list(map(formula, prd_gras))
    rct_strs = list(map(automol.formula.string, rct_fmls))
    prd_strs = list(map(automol.formula.string, prd_fmls))
    assert automol.formula.reac.is_valid_reaction(rct_fmls, prd_fmls), (
        "Invalid reaction: {:s} -> {:s}".format(str(rct_strs), str(prd_strs)))

    # Cycle through the different finders and gather all possible reactions
    finders_ = [
        trivial,
        # unimolecular reactions
        hydrogen_migrations,
        beta_scissions,
        ring_forming_scissions,
        eliminations,
        # bimolecular reactions
        hydrogen_abstractions,
        additions,
        insertions,
        substitutions,
    ]

    rxns = tuple(itertools.chain(*(f_(rct_gras, prd_gras) for f_ in finders_)))

    return rxns


def find_from_inchis(rct_ichs, prd_ichs):
    """ find all reaction classes consistent with these reactants and products

    :param rct_ichs: inchis for the reactants
    :param prd_ichs: inchis for the products
    :returns: a list of reaction classes
    :rtype: tuple[str]
    """
    rct_geos = list(map(automol.inchi.geometry, rct_ichs))
    prd_geos = list(map(automol.inchi.geometry, prd_ichs))
    rct_gras = list(map(automol.geom.connectivity_graph, rct_geos))
    prd_gras = list(map(automol.geom.connectivity_graph, prd_geos))
    rct_gras, _ = automol.graph.standard_keys_for_sequence(rct_gras)
    prd_gras, _ = automol.graph.standard_keys_for_sequence(prd_gras)
    rxns = find(rct_gras, prd_gras)
    rxn_classes = [rxn.class_ for rxn in rxns]
    rxn_classes = [c for i, c in enumerate(rxn_classes)
                   if c not in rxn_classes[:i]]
    return tuple(rxn_classes)


# helpers
def _partial_hydrogen_abstraction(qh_gra, q_gra):
    rets = []

    h_atm_key = max(atom_keys(q_gra)) + 1
    uns_atm_keys = unsaturated_atom_keys(q_gra)
    for atm_key in uns_atm_keys:
        q_gra_h = add_atom_explicit_hydrogen_keys(
            q_gra, {atm_key: [h_atm_key]})
        inv_atm_key_dct = isomorphism(q_gra_h, qh_gra)
        if inv_atm_key_dct:
            qh_q_atm_key = inv_atm_key_dct[atm_key]
            qh_h_atm_key = inv_atm_key_dct[h_atm_key]
            q_q_atm_key = atm_key
            rets.append((qh_q_atm_key, qh_h_atm_key, q_q_atm_key))

    return rets

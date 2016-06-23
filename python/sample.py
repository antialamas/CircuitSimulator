#
# file: sample.py
# construct a stabilizer decomposition of |H^(\otimes t)>
# Sample from || \Pi |H^(\otimes t)>
#

import numpy as np
from stabilizer.stabilizer import StabilizerState
from multiprocessing import Pool


def decompose(t, fidbound, k, exact, rank, fidelity):
    # trivial case
    if t == 0:
        return np.array([[]]), 1

    v = np.cos(np.pi/8)

    forceK = (k is not None)  # Was k selected by the user

    if k is None:
        # pick unique k such that 1/(2^(k-2)) \geq v^(2t) \delta \geq 1/(2^(k-1))
        k = np.ceil(1 - 2*t*np.log2(v) - np.log2(fidbound))

    # can achieve k = t/2 by pairs of stabilizer states
    if exact or (k > t/2 and not forceK):
        norm = (2)**(np.floor(t/2)/2)
        if (t % 2 == 1): norm *= (2*v)
        return None, norm

    # prevents infinite loops
    if (k > t):
        if (forceK): print("Can't have k > t. Setting k to %d." % t)
        k = t

    innerProd = 0
    Z_L = None

    while innerProd < 1-fidbound:

        L = np.random.random_integers(0, 1, (k, t))

        if (rank):
            # check rank
            if (np.linalg.matrix_rank(L) < k):
                print("L has insufficient rank. Sampling again...")
                continue

        if fidelity:
            # compute Z(L) = sum_x 2^{-|x|/2}
            Z_L = 0
            for i in range(2**k):
                z = np.array(list(np.binary_repr(i, width=k))).astype(int)[::-1]
                x = np.dot(z, L) % 2
                Z_L += 2**(-np.sum(x)/2)

            innerProd = 2**k * v**(2*t) / Z_L
            if forceK:
                print("Inner product <H^t|L>: %f" % innerProd)
                break
            elif innerProd < 1-fidbound:
                print("Inner product <H^t|L>: %f - Not good enough!" % innerProd)
            else:
                print("Inner product <H^t|L>: %f" % innerProd)
        else: break

    if fidelity:
        norm = np.sqrt(2**k * Z_L)
        return L, norm
    else:
        return L, None


# Inner product for some state in |L> ~= |H^t>
def evalLcomponent(args):
    (i, L, theta, t) = args  # unpack arguments (easier for parallel code)

    # compute bitstring by adding rows of l
    Lbits = list(np.binary_repr(i, width=len(L)))
    bitstring = np.zeros(t)
    for idx in range(len(Lbits)):
        if Lbits[idx] == '1':
            bitstring += L[idx]
    bitstring = bitstring.astype(int) % 2

    # Stabilizer state is product of |0> and |+>
    # 1's in bitstring indicate positions of |+>

    # initialize stabilizer state
    phi = StabilizerState(t, t)

    # construct state by measuring paulis
    for xtildeidx in range(t):
        vec = np.zeros(t)
        vec[xtildeidx] = 1
        if bitstring[xtildeidx] == 1:
            # |+> at index, so measure X
            phi.measurePauli(0, np.zeros(t), vec)
        else:
            # |0> at index, so measure Z
            phi.measurePauli(0, vec, np.zeros(t))

    return StabilizerState.innerProduct(theta, phi)


# Inner product for some state in |H^t> using pairwise decomposition
def evalHcomponent(args):
    (i, _, theta, t) = args  # unpack arguments (easier for parallel code)

    # import pdb; pdb.set_trace()
    size = int(np.ceil(t/2))
    odd = t % 2 == 1

    bits = list(np.binary_repr(i, width=size))

    # initialize stabilizer state
    phi = StabilizerState(t, t)

    for idx in range(size):
        bit = int(bits[idx])

        if bit == 0 and not (odd and idx == size-1):
            # phi.J = np.array([[0, 4], [4, 0]])
            phi.J[idx*2+1, idx*2] = 4
            phi.J[idx*2, idx*2+1] = 4

    for idx in range(size):
        bit = int(bits[idx])
        vec = np.zeros(t)

        if odd and idx == size-1:
            vec[t-1] = 1
            # last qubit: |H> = (1/2v)(|0> + |+>)
            if bit == 0:
                phi.measurePauli(0, vec, np.zeros(t))  # |0>, measure Z
            else:
                phi.measurePauli(0, np.zeros(t), vec)  # |+>, measure X

            continue

        if bit == 0: continue

        vec[idx*2+1] = 1
        vec[idx*2] = 1

        phi.measurePauli(0, np.zeros(t), vec)  # measure XX
        phi.measurePauli(0, vec, np.zeros(t))  # measure ZZ

    return StabilizerState.innerProduct(theta, phi)


# Evaluate || <theta| P |H^t> ||^2 for a random stabilizer state theta.
def sampleProjector(args):
    (P, L, seed, parallel) = args  # unpack arguments (easier for parallel code)
    (phases, xs, zs) = P

    # empty projector
    if len(phases) == 0:
        return 1

    t = len(xs[0])

    # clifford circuit
    if t == 0:
        lookup = {0: 1, 2: -1}
        generators = [1]  # include identity
        for phase in phases: generators.append(lookup[phase])

        # calculate sum of all permutations of generators
        return sum(generators)/len(generators)

    # set unique seed for this calculation
    np.random.seed((seed) % 4294967296)

    # sample random theta
    theta = StabilizerState.randomStabilizerState(t)

    # project random state to P
    projfactor = 1
    for g in range(len(phases)):
        res = theta.measurePauli(phases[g], zs[g], xs[g])
        projfactor *= res

        if res == 0: return 0  # theta annihilated by P

    if L is None:  # use exact decomp into pairs of stabilizer states
        func = evalHcomponent
        size = int(np.ceil(t/2))  # need one bit for each pair, plus one more if t is odd
    else:
        func = evalLcomponent
        size = len(L)

    parallel = False

    if parallel:  # parallelize for large enough L
        pool = Pool()
        total = sum(pool.map(func, [(i, L, theta, t) for i in range(0, 2**size)]))
        pool.close()
        pool.join()
    else:
        total = sum(map(func, [(i, L, theta, t) for i in range(0, 2**size)]))

    return 2**t * np.abs(projfactor*total)**2
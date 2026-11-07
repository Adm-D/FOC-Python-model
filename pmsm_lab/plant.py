"""Switching three-phase star-connected PMSM, RK4 with exact PWM edge splitting.

The uniform output grid never replaces the switching edges: each integration
interval is split at all bridge events inside it. No fastmath, clipping of plant
states or ideal speed-source substitution is used.
"""
import math
import numpy as np
from numba import njit


@njit(cache=True)
def derivative(y, va, vb, vc, load, p):
    r, ld, lq, flux, pairs, inertia, friction = p
    id_, iq, omega, theta = y
    alpha = (2 * va - vb - vc) / 3
    beta = (vb - vc) / math.sqrt(3)
    c, s = math.cos(theta), math.sin(theta)
    vd, vq = c * alpha + s * beta, -s * alpha + c * beta
    we = pairs * omega
    te = 1.5 * pairs * (flux * iq + (ld - lq) * id_ * iq)
    return np.array([(vd - r * id_ + we * lq * iq) / ld,
                     (vq - r * iq - we * (ld * id_ + flux)) / lq,
                     (te - load - friction * omega) / inertia, we])


@njit(cache=True)
def rk4(y, h, va, vb, vc, load0, load1, p):
    km = (load0 + load1) / 2
    k1 = derivative(y, va, vb, vc, load0, p)
    k2 = derivative(y + h * k1 / 2, va, vb, vc, km, p)
    k3 = derivative(y + h * k2 / 2, va, vb, vc, km, p)
    k4 = derivative(y + h * k3, va, vb, vc, load1, p)
    return y + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


@njit(cache=True)
def bridge(phase, duties, vdc):
    carrier = 1 - abs(2 * phase - 1)
    a = 1.0 if duties[0] > carrier else 0.0
    b = 1.0 if duties[1] > carrier else 0.0
    c = 1.0 if duties[2] > carrier else 0.0
    neutral = (a + b + c) / 3
    return (a - neutral) * vdc, (b - neutral) * vdc, (c - neutral) * vdc, a, b, c, carrier


@njit(cache=True)
def pwm_period(y, duties, vdc, period, substeps, loads, p, output, offset, linear_load=False):
    edges = np.sort(np.array([duties[0] / 2, duties[1] / 2, duties[2] / 2,
                             1 - duties[0] / 2, 1 - duties[1] / 2, 1 - duties[2] / 2]))
    mean = np.zeros(3)
    for j in range(substeps):
        left, right = j / substeps, (j + 1) / substeps
        row = offset + j
        output[row, :4] = y
        output[row, 4:] = bridge(left, duties, vdc)
        old = y[:3].copy()
        a = left
        # An extra sentinel closes the current integration interval.
        for k in range(7):
            b = right if k == 6 else edges[k]
            if b <= a or b > right:
                continue
            va, vb, vc, _, _, _, _ = bridge((a + b) / 2, duties, vdc)
            fa, fb = (a - left) * substeps, (b - left) * substeps
            delta = loads[j + 1] - loads[j] if linear_load else 0.
            load_a = loads[j] + fa * delta
            load_b = loads[j] + fb * delta
            y = rk4(y, (b - a) * period, va, vb, vc, load_a, load_b, p)
            a = b
        mean += (old + y[:3]) / (2 * substeps)
    return y, mean

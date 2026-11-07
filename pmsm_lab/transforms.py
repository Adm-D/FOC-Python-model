"""Amplitude-invariant transforms, a-axis aligned with d at theta_e = 0.

Power: v_a i_a + v_b i_b + v_c i_c = 3/2 (v_d i_d + v_q i_q)
for a balanced three-wire system. Angles are electrical radians.
"""
import math


def clarke(a: float, b: float, c: float) -> tuple[float, float]:
    return (2 * a - b - c) / 3, (b - c) / math.sqrt(3)


def inverse_clarke(alpha: float, beta: float) -> tuple[float, float, float]:
    return alpha, -alpha / 2 + math.sqrt(3) * beta / 2, -alpha / 2 - math.sqrt(3) * beta / 2


def park(alpha: float, beta: float, theta: float) -> tuple[float, float]:
    c, s = math.cos(theta), math.sin(theta)
    return c * alpha + s * beta, -s * alpha + c * beta


def inverse_park(d: float, q: float, theta: float) -> tuple[float, float]:
    c, s = math.cos(theta), math.sin(theta)
    return c * d - s * q, s * d + c * q


def svpwm(d: float, q: float, theta: float, vdc: float):
    """Centered carrier PWM with min/max zero-sequence injection (linear SVPWM)."""
    abc = inverse_clarke(*inverse_park(d, q, theta))
    offset = -(max(abc) + min(abc)) / 2
    return tuple(min(1.0, max(0.0, 0.5 + (v + offset) / vdc)) for v in abc)

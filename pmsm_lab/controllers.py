"""Replaceable controller boundary. A future RL policy only implements Controller.

One observation/action every PWM period; SI units; perfect rotor measurement.
The simulator ALWAYS imposes a voltage circle and complementary bridge gates.
"""
import math
from dataclasses import dataclass
from typing import Protocol

from .config import MotorParameters, FOCSettings


@dataclass(frozen=True)
class Observation:
    time: float
    id: float
    iq: float
    omega: float
    theta_e: float
    speed_reference: float  # mechanical rad/s
    vdc: float


@dataclass(frozen=True)
class VoltageCommand:
    vd: float
    vq: float
    id_reference: float = 0.0
    iq_reference: float = 0.0
    saturated: bool = False


class Controller(Protocol):
    def reset(self, motor: MotorParameters, sample_time: float) -> None: ...
    def step(self, observation: Observation) -> VoltageCommand: ...


def clip(x, limit):
    return max(-limit, min(limit, x))


class FOCController:
    """Cascaded speed/current PI, feedforward decoupling and back-calculation.

    Current feedback is averaged over the preceding PWM cycle. Current integral
    tracking time 1/w_ci; speed tracking time 1/w_n. No field weakening or MTPA.
    """
    def __init__(self, settings: FOCSettings | None = None):
        self.settings = settings or FOCSettings()

    def reset(self, motor: MotorParameters, sample_time: float):
        self.m, self.dt = motor, sample_time
        self.zd = self.zq = self.zw = 0.0
        self.wci = 2 * math.pi * self.settings.current_bandwidth_hz
        self.wn = 2 * math.pi * self.settings.speed_bandwidth_hz
        kt = 1.5 * motor.pole_pairs * (motor.flux + (motor.ld - motor.lq) * self.settings.id_reference)
        if kt <= 0:
            raise ValueError("FOC: неположительный коэффициент момента при выбранном id*.")
        self.kpw = 2 * self.settings.damping * self.wn * motor.inertia / kt
        self.kiw = self.wn**2 * motor.inertia / kt

    def step(self, o: Observation) -> VoltageCommand:
        m, s = self.m, self.settings
        ew = o.speed_reference - o.omega
        raw_iq = self.kpw * ew + self.zw
        iq_limit = math.sqrt(m.current_limit**2 - s.id_reference**2)
        iq_ref = clip(raw_iq, iq_limit)
        self.zw += self.dt * (self.kiw * ew + self.wn * (iq_ref - raw_iq))
        ed, eq = s.id_reference - o.id, iq_ref - o.iq
        we = m.pole_pairs * o.omega
        vd_ff = -we * m.lq * o.iq if s.decoupling else 0.0
        vq_ff = we * (m.ld * o.id + m.flux) if s.decoupling else 0.0
        vd = m.ld * self.wci * ed + self.zd + vd_ff
        vq = m.lq * self.wci * eq + self.zq + vq_ff
        scale = min(1.0, o.vdc / math.sqrt(3) / max(math.hypot(vd, vq), 1e-30))
        ud, uq = vd * scale, vq * scale
        self.zd += self.dt * (m.resistance * self.wci * ed + self.wci * (ud - vd))
        self.zq += self.dt * (m.resistance * self.wci * eq + self.wci * (uq - vq))
        # Freeze further acceleration of speed integrator while voltage is limiting
        # in the same direction as requested torque; tracking still unwinds it.
        if scale < 1 and ew * iq_ref > 0:
            self.zw -= self.dt * self.kiw * ew
        return VoltageCommand(ud, uq, s.id_reference, iq_ref,
                              scale < 1 or abs(raw_iq) > iq_limit)

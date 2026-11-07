"""Validated simulation inputs and traceable catalog-to-model assumptions."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


CATALOG = {
    "3V": dict(voltage=3.0, no_load_rpm=35300, no_load_A=0.0288,
               nominal_rpm=12100, nominal_mNm=0.229, nominal_A=0.322,
               stall_mNm=0.367, stall_A=0.481, resistance_terminal=6.23,
               inductance_terminal_mH=0.0749, kt_mNm_A=0.763, kv_rpm_V=12500,
               mechanical_time_ms=1.19, efficiency_percent=58.1),
    "6V": dict(voltage=6.0, no_load_rpm=35400, no_load_A=0.0144,
               nominal_rpm=13400, nominal_mNm=0.239, nominal_A=0.167,
               stall_mNm=0.403, stall_A=0.264, resistance_terminal=22.8,
               inductance_terminal_mH=0.285, kt_mNm_A=1.53, kv_rpm_V=6240,
               mechanical_time_ms=1.08, efficiency_percent=59.7),
}
CATALOG_COMMON = dict(rotor_inertia_gcm2=0.00111, pole_pairs=1, phases=3,
                      max_rpm=50000, weight_g=1.2, thermal_winding_housing_K_W=15.2,
                      thermal_housing_ambient_K_W=96.7, thermal_winding_s=0.738,
                      thermal_motor_s=58.5, max_winding_C=125)


class MotorParameters(StrictModel):
    resistance: float = Field(default=3.115, gt=0, le=1000, description="Phase R [ohm]")
    ld: float = Field(default=0.00003745, gt=1e-9, le=1, description="Ld [H]")
    lq: float = Field(default=0.00003745, gt=1e-9, le=1, description="Lq [H]")
    flux: float = Field(default=0.000763 / math.sqrt(3), gt=1e-8, le=10, description="PM flux [Wb]")
    pole_pairs: int = Field(default=1, ge=1, le=100)
    inertia: float = Field(default=1.11e-10, gt=1e-14, le=100, description="J [kg m2]")
    friction: float = Field(default=0.000763 * 0.0288 / (35300 * math.pi / 30), ge=0, le=10)
    vdc: float = Field(default=3.0, gt=0, le=1500)
    current_limit: float = Field(default=2 * 0.481 / math.sqrt(3), gt=0, le=10000,
                                 description="dq vector / phase peak command limit [A]")
    continuous_rms: float = Field(default=0.322 * math.sqrt(2 / 3), gt=0, le=10000)
    max_rpm: float = Field(default=50000, gt=0, le=1e7)


def motor_preset(name: str) -> MotorParameters:
    c = CATALOG[name]
    return MotorParameters(
        resistance=c["resistance_terminal"] / 2,
        ld=c["inductance_terminal_mH"] * 1e-3 / 2,
        lq=c["inductance_terminal_mH"] * 1e-3 / 2,
        flux=c["kt_mNm_A"] * 1e-3 / math.sqrt(3),
        friction=c["kt_mNm_A"] * 1e-3 * c["no_load_A"] / (c["no_load_rpm"] * math.pi / 30),
        vdc=c["voltage"], current_limit=2 * c["stall_A"] / math.sqrt(3),
        continuous_rms=c["nominal_A"] * math.sqrt(2 / 3),
    )


class Event(StrictModel):
    time: float = Field(ge=0)
    value: float


class FOCSettings(StrictModel):
    current_bandwidth_hz: float = Field(default=5000, gt=0)
    speed_bandwidth_hz: float = Field(default=150, gt=0)
    damping: float = Field(default=1.0, ge=0.2, le=3)
    id_reference: float = 0.0
    decoupling: bool = True


class SimulationConfig(StrictModel):
    preset: Literal["3V", "6V", "custom"] = "3V"
    motor: MotorParameters = Field(default_factory=MotorParameters)
    foc: FOCSettings = Field(default_factory=FOCSettings)
    duration: float = Field(default=0.12, ge=0.001, le=2)
    pwm_hz: int = Field(default=100000, ge=1000, le=500000)
    substeps: int = Field(default=40, ge=20, le=500)
    initial_rpm: float = Field(default=0.0, ge=-1e6, le=1e6)
    initial_angle: float = 0.0
    speed: list[Event] = Field(default_factory=lambda: [Event(time=0, value=12000),
        Event(time=.04, value=22000), Event(time=.08, value=16000)], min_length=1, max_length=100)
    load: list[Event] = Field(default_factory=lambda: [Event(time=0, value=0),
        Event(time=.06, value=0.00008), Event(time=.10, value=0.00014)], min_length=1, max_length=100)
    interpolation: Literal["step", "linear"] = "step"

    @model_validator(mode="after")
    def physical_resolution(self):
        if self.duration * self.pwm_hz * self.substeps > 1_200_000:
            raise ValueError("Лимит 1 200 000 шагов. Уменьшите длительность, ШИМ или число подшагов.")
        dt = 1 / (self.pwm_hz * self.substeps)
        if dt > min(self.motor.ld, self.motor.lq) / self.motor.resistance / 10:
            raise ValueError("Шаг должен быть ≤ min(Ld,Lq)/(10R). Увеличьте число подшагов.")
        if self.foc.current_bandwidth_hz > self.pwm_hz / 10:
            raise ValueError("Полоса контура тока должна быть ≤ fPWM/10.")
        if self.foc.speed_bandwidth_hz > self.foc.current_bandwidth_hz / 5:
            raise ValueError("Полоса контура скорости должна быть ≤ полосы тока / 5.")
        if abs(self.foc.id_reference) >= self.motor.current_limit:
            raise ValueError("|id*| должен быть меньше ограничения тока.")
        for name in ["speed", "load"]:
            events = getattr(self, name)
            if events[0].time != 0 or any(a.time >= b.time for a, b in zip(events, events[1:])):
                raise ValueError(f"{name}: первая точка t=0, следующие строго по возрастанию.")
            if events[-1].time >= self.duration:
                raise ValueError(f"{name}: все события должны быть раньше конца расчёта.")
        if any(abs(e.value) > 1e6 for e in self.speed):
            raise ValueError("|n*| ≤ 1 000 000 rpm.")
        if any(abs(e.value) > 100 for e in self.load):
            raise ValueError("|Tload| ≤ 100 N m.")
        return self

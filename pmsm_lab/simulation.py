"""Deterministic simulation API, independent of the HTTP application."""
from dataclasses import dataclass
import math
import time

import numpy as np

from .config import SimulationConfig
from .controllers import Controller, FOCController, Observation
from .plant import pwm_period, bridge
from .transforms import svpwm


def schedule(events, times, interpolation):
    ts = np.array([e.time for e in events])
    vs = np.array([e.value for e in events])
    if interpolation == 'linear':
        return np.interp(times, ts, vs)
    return vs[np.clip(np.searchsorted(ts, times + 1e-14, side='right') - 1, 0, len(vs) - 1)]


@dataclass
class SimulationResult:
    config: SimulationConfig
    time: np.ndarray
    signals: dict[str, np.ndarray]
    metrics: dict
    warnings: list[str]

    def window(self, names, start=0.0, end=None, limit=2000):
        """Common indices retaining per-bin extrema of ALL selected traces.

        A reduced trace is for overview, not spectral analysis. Gate/PWM details
        should be requested over a narrow interval to return the original grid.
        """
        end = self.time[-1] if end is None else end
        lo = int(np.searchsorted(self.time, start, side='left'))
        hi = int(np.searchsorted(self.time, end, side='right'))
        idx = np.arange(lo, hi)
        raw_count = len(idx)
        if raw_count > limit:
            bins = max(1, limit // (2 * len(names) + 2))
            edges = np.linspace(lo, hi, bins + 1, dtype=int)
            kept = [lo, hi - 1]
            for a, b in zip(edges, edges[1:]):
                if b <= a:
                    continue
                kept.extend([a, b - 1])
                for name in names:
                    x = self.signals[name][a:b]
                    kept.extend([a + int(np.argmin(x)), a + int(np.argmax(x))])
            idx = np.unique(kept)
        return dict(time=self.time[idx].tolist(), signals={n: self.signals[n][idx].tolist() for n in names},
                    raw_count=raw_count, returned_count=len(idx), reduced=len(idx) < raw_count,
                    dt=float(self.time[1] - self.time[0]))


def simulate(config: SimulationConfig, controller: Controller | None = None) -> SimulationResult:
    started = time.perf_counter()
    c, m = config, config.motor
    period = 1 / c.pwm_hz
    cycles = int(math.ceil(c.duration * c.pwm_hz - 1e-9))
    n = cycles * c.substeps
    t = np.arange(n + 1, dtype=np.float64) * period / c.substeps
    speed = schedule(c.speed, t, c.interpolation)
    load = schedule(c.load, t, c.interpolation)
    raw = np.zeros((n + 1, 11), dtype=np.float64)
    commands = np.zeros((cycles, 10), dtype=np.float64)
    y = np.array([0., 0., c.initial_rpm * math.pi / 30, c.initial_angle])
    avg = y[:3].copy()
    p = np.array([m.resistance, m.ld, m.lq, m.flux, m.pole_pairs, m.inertia, m.friction])
    controller = controller if controller is not None else FOCController(c.foc)
    controller.reset(m, period)
    for cycle in range(cycles):
        j = cycle * c.substeps
        obs = Observation(t[j], avg[0], avg[1], avg[2], y[3], speed[j] * math.pi / 30, m.vdc)
        cmd = controller.step(obs)
        if not all(math.isfinite(x) for x in [cmd.vd, cmd.vq, cmd.id_reference, cmd.iq_reference]):
            raise ValueError('Контроллер вернул NaN/Inf.')
        scale = min(1., m.vdc / math.sqrt(3) / max(math.hypot(cmd.vd, cmd.vq), 1e-30))
        vd, vq = cmd.vd * scale, cmd.vq * scale
        duties = np.array(svpwm(vd, vq, y[3], m.vdc))
        # Inverse transforms are evaluated at the sampled rotor position and held.
        alpha = math.cos(y[3]) * vd - math.sin(y[3]) * vq
        beta = math.sin(y[3]) * vd + math.cos(y[3]) * vq
        commands[cycle] = [vd, vq, cmd.id_reference, cmd.iq_reference, *duties,
                           alpha, beta, float(cmd.saturated or scale < 1)]
        y, avg = pwm_period(y, duties, m.vdc, period, c.substeps,
                            load[j:j + c.substeps + 1], p, raw, j, c.interpolation == 'linear')
        if not np.isfinite(y).all() or np.max(np.abs(y[:3])) > 1e9:
            raise ValueError('Расчёт расходится: уменьшите шаг или проверьте параметры двигателя и нагрузки.')
    raw[-1, :4] = y
    raw[-1, 4:] = bridge(0., duties, m.vdc)
    held = np.vstack([np.repeat(commands, c.substeps, axis=0), commands[-1]])
    id_, iq, omega, theta = raw[:, :4].T
    va, vb, vc = raw[:, 4:7].T
    co, si = np.cos(theta), np.sin(theta)
    ialpha, ibeta = co * id_ - si * iq, si * id_ + co * iq
    ia, ib, ic = ialpha, -.5 * ialpha + math.sqrt(3)/2 * ibeta, -.5 * ialpha - math.sqrt(3)/2 * ibeta
    valpha, vbeta = (2 * va - vb - vc)/3, (vb - vc)/math.sqrt(3)
    we = m.pole_pairs * omega
    ealpha, ebeta = -si * we * m.flux, co * we * m.flux
    te = 1.5 * m.pole_pairs * (m.flux * iq + (m.ld - m.lq) * id_ * iq)
    ar, br = held[:, 7], held[:, 8]
    sig = dict(speed_rpm=omega * 30/math.pi, speed_ref_rpm=speed,
        torque=te, load_torque=load, friction_torque=m.friction * omega, shaft_torque=te - m.friction * omega,
        ia=ia, ib=ib, ic=ic, i_alpha=ialpha, i_beta=ibeta, id=id_, iq=iq,
        va=va, vb=vb, vc=vc, vab=va-vb, vbc=vb-vc, vca=vc-va,
        v_alpha=valpha, v_beta=vbeta, vd=co*valpha+si*vbeta, vq=-si*valpha+co*vbeta,
        ea=ealpha, eb=-.5*ealpha+math.sqrt(3)/2*ebeta, ec=-.5*ealpha-math.sqrt(3)/2*ebeta,
        vd_ref=held[:, 0], vq_ref=held[:, 1], id_ref=held[:, 2], iq_ref=held[:, 3],
        duty_a=held[:, 4], duty_b=held[:, 5], duty_c=held[:, 6], carrier=raw[:, 10],
        v_alpha_ref=ar, v_beta_ref=br, va_ref=ar, vb_ref=-ar/2+math.sqrt(3)/2*br, vc_ref=-ar/2-math.sqrt(3)/2*br,
        sah=raw[:, 7], sal=1-raw[:, 7], sbh=raw[:, 8], sbl=1-raw[:, 8], sch=raw[:, 9], scl=1-raw[:, 9],
        theta_e=theta, omega_e=we, p_electric=va*ia+vb*ib+vc*ic,
        p_copper=m.resistance*(ia*ia+ib*ib+ic*ic), p_mechanical=te*omega,
        p_friction=m.friction*omega**2, p_load=load*omega,
        p_dc=m.vdc*(raw[:, 7]*ia+raw[:, 8]*ib+raw[:, 9]*ic),
        energy=.75*(m.ld*id_**2+m.lq*iq**2)+.5*m.inertia*omega**2)
    tail = slice(max(0, n - int(.005/period)*c.substeps), n + 1)
    rms = float(np.sqrt(np.mean((ia**2+ib**2+ic**2)/3)))
    tail_rms = float(np.sqrt(np.mean((ia[tail]**2+ib[tail]**2+ic[tail]**2)/3)))
    warnings = ['Синусоидальная PMSM-аппроксимация BLDC: параметры d/q и форма ЭДС требуют экспериментальной идентификации.']
    if max(rms, tail_rms) > m.continuous_rms:
        warnings.append('Действующий ток превышает заданный длительный предел; тепловая модель не рассчитывается.')
    if np.max(np.abs(sig['speed_rpm'])) > m.max_rpm:
        warnings.append('Превышена паспортная механическая скорость.')
    error = float(np.mean(sig['speed_rpm'][tail] - speed[tail]))
    if abs(error) > max(100, abs(speed[-1]) * .02):
        warnings.append('В последние 5 мс скорость не достигла задания: проверьте насыщение, нагрузку и время установления.')
    metrics = dict(samples=n+1, dt=period/c.substeps, duration=float(t[-1]),
        runtime_s=time.perf_counter()-started, final_rpm=float(sig['speed_rpm'][-1]),
        final_reference_rpm=float(speed[-1]), mean_tail_rpm=float(np.mean(sig['speed_rpm'][tail])),
        speed_error_rpm=error, rms_current_A=rms, tail_rms_current_A=tail_rms,
        peak_current_A=float(max(np.max(np.abs(ia)),np.max(np.abs(ib)),np.max(np.abs(ic)))),
        mean_tail_torque_Nm=float(np.mean(te[tail])), saturation_percent=float(100*np.mean(commands[:,9])))
    return SimulationResult(c, t, sig, metrics, warnings)

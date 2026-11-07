"""Example plug-in boundary, NOT a trained policy or an RL training environment.

Pass a callable policy(observation_vector) -> normalized (vd, vq).
Observation scaling here is an example that must match the agent's training.
"""
import math
import numpy as np
from pmsm_lab.controllers import Observation, VoltageCommand


class RLPolicyController:
    def __init__(self, policy):
        self.policy = policy

    def reset(self, motor, sample_time):
        self.motor, self.sample_time = motor, sample_time
        if hasattr(self.policy, 'reset'):
            self.policy.reset()

    def step(self, o: Observation) -> VoltageCommand:
        m = self.motor
        max_speed = m.max_rpm * math.pi / 30
        state = np.array([o.id/m.current_limit, o.iq/m.current_limit,
                          o.omega/max_speed, o.speed_reference/max_speed,
                          math.sin(o.theta_e), math.cos(o.theta_e)], dtype=np.float32)
        action = np.asarray(self.policy(state), dtype=float)
        if action.shape != (2,) or not np.isfinite(action).all():
            raise ValueError('Policy must return two finite normalized voltages.')
        voltage = np.clip(action, -1, 1) * o.vdc / math.sqrt(3)
        # The simulation applies the final circular voltage limit for all policies.
        return VoltageCommand(float(voltage[0]), float(voltage[1]))

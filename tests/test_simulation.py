import math
import numpy as np
import pytest
from pydantic import ValidationError

from pmsm_lab.config import SimulationConfig, Event, motor_preset
from pmsm_lab.controllers import VoltageCommand
from pmsm_lab.simulation import simulate, schedule
from pmsm_lab.signals import SIGNALS


def simple_config(**updates):
    cfg=SimulationConfig(duration=.03,speed=[Event(time=0,value=12000)],
                         load=[Event(time=0,value=0),Event(time=.015,value=.00010)])
    return SimulationConfig.model_validate({**cfg.model_dump(),**updates})


@pytest.fixture(scope='module')
def nominal():
    return simulate(simple_config())


def test_foc_tracking_and_load_rejection(nominal):
    r=nominal;s=r.signals
    assert abs(r.metrics['speed_error_rpm'])<120
    assert abs(np.mean(s['id'][-10000:]))<.005
    assert np.mean(s['torque'][-10000:])==pytest.approx(.0001+r.config.motor.friction*12000*math.pi/30,rel=.03)
    assert r.time[0]==0 and r.time[-1]==pytest.approx(.03)
    assert set(s)==set(SIGNALS)
    assert all(np.isfinite(v).all() for v in s.values())


def test_actual_inverter_and_power(nominal):
    s=nominal.signals;m=nominal.config.motor
    np.testing.assert_allclose(s['ia']+s['ib']+s['ic'],0,atol=1e-14)
    np.testing.assert_allclose(s['va']+s['vb']+s['vc'],0,atol=1e-14)
    for phase in ['a','b','c']:
        h=s[f's{phase}h'];l=s[f's{phase}l']
        assert set(np.unique(h))=={0,1}
        np.testing.assert_array_equal(h+l,1)
        expected=m.vdc*(h-(s['sah']+s['sbh']+s['sch'])/3)
        np.testing.assert_allclose(s[f'v{phase}'],expected,atol=1e-14)
    np.testing.assert_allclose(s['p_dc'],s['p_electric'],atol=1e-14)
    assert np.max(np.hypot(s['vd_ref'],s['vq_ref']))<=m.vdc/math.sqrt(3)+1e-12


def test_six_volt_preset():
    r=simulate(simple_config(motor=motor_preset('6V').model_dump(),preset='6V'))
    assert abs(r.metrics['speed_error_rpm'])<120


def test_reverse_and_recovery_from_voltage_saturation():
    r=simulate(simple_config(duration=.06,speed=[{'time':0,'value':100000},
                      {'time':.025,'value':-10000}],load=[{'time':0,'value':0}]))
    assert abs(r.metrics['speed_error_rpm'])<150
    assert r.metrics['saturation_percent']>10
    assert np.min(r.signals['torque'])<0


def test_convergence_when_halving_step():
    c=simple_config(duration=.006,load=[{'time':0,'value':.00005}])
    a=simulate(SimulationConfig.model_validate({**c.model_dump(),'substeps':20}))
    b=simulate(SimulationConfig.model_validate({**c.model_dump(),'substeps':40}))
    assert abs(a.metrics['final_rpm']-b.metrics['final_rpm'])<2
    assert abs(a.metrics['rms_current_A']-b.metrics['rms_current_A'])<.002


def test_replaceable_controller_and_final_voltage_limit():
    class ExternalPolicy:
        def reset(self,motor,sample_time): self.dt=sample_time;self.steps=0
        def step(self,o):
            self.steps+=1
            return VoltageCommand(0.,1000.)
    policy=ExternalPolicy()
    c=simple_config(duration=.002,load=[{'time':0,'value':0}])
    r=simulate(c,policy)
    assert policy.steps==200
    assert np.max(r.signals['vq_ref'])<=c.motor.vdc/math.sqrt(3)+1e-12
    assert r.metrics['final_rpm']>100


def test_sampling_preserves_spikes_and_detail(nominal):
    overview=nominal.window(['ia','ib','ic'],limit=500)
    assert overview['reduced'] and overview['returned_count']<=502
    assert max(overview['signals']['ia'])==np.max(nominal.signals['ia'])
    detail=nominal.window(['sah','sal'],.0299,.03,2000)
    assert not detail['reduced']
    assert detail['raw_count']>300


def test_step_and_linear_schedules():
    e=[Event(time=0,value=10),Event(time=.01,value=20)]
    t=np.array([0,.005,.01,.02])
    np.testing.assert_allclose(schedule(e,t,'step'),[10,10,20,20])
    np.testing.assert_allclose(schedule(e,t,'linear'),[10,15,20,20])
    r=simulate(simple_config(interpolation='linear'))
    assert np.isfinite(r.signals['torque']).all()


@pytest.mark.parametrize('updates',[
    {'duration':2}, {'pwm_hz':1000}, {'substeps':1},
    {'speed':[{'time':.001,'value':1000}]},
    {'load':[{'time':0,'value':0},{'time':.03,'value':0}]},
    {'motor':{**motor_preset('3V').model_dump(),'resistance':-1}},
    {'motor':{**motor_preset('3V').model_dump(),'flux':float('nan')}},
])
def test_invalid_configuration_is_rejected(updates):
    with pytest.raises(ValidationError):simple_config(**updates)

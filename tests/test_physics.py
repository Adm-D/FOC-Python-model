import math
import numpy as np
import pytest

from pmsm_lab.config import MotorParameters, motor_preset
from pmsm_lab.transforms import clarke, inverse_clarke, park, inverse_park, svpwm
from pmsm_lab.plant import derivative, rk4, bridge


def params(m):
    return np.array([m.resistance,m.ld,m.lq,m.flux,m.pole_pairs,m.inertia,m.friction])


def test_transform_roundtrip_and_power():
    rng=np.random.default_rng(42)
    for _ in range(100):
        i=rng.normal(size=3);i-=i.mean()
        v=rng.normal(size=3);v-=v.mean()
        theta=rng.uniform(-10,10)
        np.testing.assert_allclose(inverse_clarke(*clarke(*i)),i,atol=1e-14)
        d,q=park(*clarke(*i),theta)
        np.testing.assert_allclose(inverse_park(d,q,theta),clarke(*i),atol=1e-14)
        vd,vq=park(*clarke(*v),theta)
        assert np.dot(v,i)==pytest.approx(1.5*(vd*d+vq*q),abs=1e-13)


def test_terminal_conversion_and_units():
    m=motor_preset('3V')
    assert m.inertia==pytest.approx(1.11e-10)
    assert m.ld==pytest.approx(37.45e-6)
    assert m.resistance==pytest.approx(3.115)
    assert 1.5*m.pole_pairs*m.flux*(2*.322/math.sqrt(3))==pytest.approx(.763e-3*.322)
    # Same copper loss in equivalent 120° commutation and sinusoidal dq model.
    iq=2*.322/math.sqrt(3)
    assert 1.5*m.resistance*iq**2==pytest.approx(6.23*.322**2)
    assert motor_preset('6V').ld==pytest.approx(142.5e-6)


def test_locked_rotor_rl_analytic_solution():
    m=MotorParameters()
    p=params(m);y=np.zeros(4);h=1e-7;steps=500
    # d-axis voltage, no q current or torque, hence rotor remains at rest.
    for _ in range(steps):y=rk4(y,h,1.,-.5,-.5,0.,0.,p)
    exact=(1-math.exp(-m.resistance*steps*h/m.ld))/m.resistance
    assert y[0]==pytest.approx(exact,rel=1e-9)
    np.testing.assert_allclose(y[1:],0,atol=1e-15)


def test_dq_energy_balance_with_saliency():
    m=MotorParameters(ld=40e-6,lq=65e-6)
    y=np.array([.07,.18,1600.,.73])
    abc=inverse_clarke(*inverse_park(.4,1.1,y[3]))
    dy=derivative(y,*abc,.00008,params(m))
    dW=1.5*(m.ld*y[0]*dy[0]+m.lq*y[1]*dy[1])+m.inertia*y[2]*dy[2]
    pel=1.5*(.4*y[0]+1.1*y[1])
    losses=1.5*m.resistance*(y[0]**2+y[1]**2)+.00008*y[2]+m.friction*y[2]**2
    assert dW==pytest.approx(pel-losses,abs=1e-14)


def test_back_emf_power_equals_pm_torque_power():
    m=MotorParameters();omega=2000.;iq=.2;theta=.4
    emf=inverse_clarke(*inverse_park(0,m.pole_pairs*omega*m.flux,theta))
    currents=inverse_clarke(*inverse_park(.1,iq,theta))
    assert np.dot(emf,currents)==pytest.approx(1.5*m.pole_pairs*m.flux*iq*omega)


@pytest.mark.parametrize('theta',[0,.41,2.,5.8])
def test_svpwm_mean_voltage_matches_inverse_transforms(theta):
    d,q=.43,.91
    duties=np.array(svpwm(d,q,theta,3.))
    edges=sorted(set([0.,1.,*list(duties/2),*list(1-duties/2)]))
    mean=np.zeros(3)
    for a,b in zip(edges,edges[1:]):
        v=np.array(bridge((a+b)/2,duties,3.)[:3]);mean+=(b-a)*v
    expected=inverse_clarke(*inverse_park(d,q,theta))
    np.testing.assert_allclose(mean,expected,atol=1e-14)

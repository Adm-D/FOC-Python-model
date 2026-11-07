"""Public signal dictionary: label, SI unit, and graph group."""

SIGNALS = {}


def add(names, labels, unit, group):
    for name, label in zip(names.split(), labels.split('|')):
        SIGNALS[name] = dict(label=label, unit=unit, group=group)


add('speed_rpm speed_ref_rpm', 'n|n*', 'rpm', 'speed')
add('torque load_torque friction_torque shaft_torque', 'Tₑ|Tₗ|Bω|Tₑ − Bω', 'N·m', 'torque')
add('ia ib ic', 'iₐ|iᵦ|i꜀', 'A', 'currents')
add('va vb vc', 'vₐₙ|vᵦₙ|v꜀ₙ', 'V', 'voltages')
add('vab vbc vca', 'vₐᵦ|vᵦ꜀|v꜀ₐ', 'V', 'line_voltages')
add('ea eb ec', 'eₐ|eᵦ|e꜀', 'V', 'emf')
add('id iq id_ref iq_ref', 'i_d|i_q|i_d*|i_q*', 'A', 'dq_current')
add('i_alpha i_beta', 'i_α|i_β', 'A', 'clarke_current')
add('vd vq vd_ref vq_ref', 'v_d|v_q|v_d*|v_q*', 'V', 'dq_voltage')
add('v_alpha v_beta', 'v_α|v_β', 'V', 'clarke_voltage')
add('v_alpha_ref v_beta_ref', 'v_α*|v_β*', 'V', 'inverse_park')
add('va_ref vb_ref vc_ref', 'vₐ*|vᵦ*|v꜀*', 'V', 'inverse_clarke')
add('sah sal sbh sbl sch scl', 'A+|A−|B+|B−|C+|C−', '0/1', 'gates')
add('duty_a duty_b duty_c carrier', 'dₐ|dᵦ|d꜀|carrier', '1', 'pwm')
add('p_electric p_copper p_mechanical p_friction p_load p_dc',
    'Pₑₗ|P꜀ᵤ|Tₑω|Bω²|Tₗω|Pdc', 'W', 'power')
add('theta_e', 'θₑ', 'rad', 'rotor')
add('omega_e', 'ωₑ', 'rad/s', 'rotor')
add('energy', 'Wmag + Wkin', 'J', 'energy')

GROUPS = {
    'speed': 'Скорость ротора', 'torque': 'Момент на валу', 'currents': 'Фазные токи',
    'voltages': 'Напряжения обмоток', 'line_voltages': 'Линейные напряжения',
    'emf': 'Обратная ЭДС', 'dq_current': 'Токи d/q', 'clarke_current': 'Кларк · токи α/β',
    'dq_voltage': 'Парк · напряжения d/q', 'clarke_voltage': 'Кларк · напряжения α/β',
    'inverse_park': 'Обратный Парк · α/β', 'inverse_clarke': 'Обратный Кларк · abc',
    'gates': 'Шесть ключей инвертора', 'pwm': 'ШИМ · заполнение и несущая',
    'power': 'Мощность и потери', 'rotor': 'Электрический угол и скорость',
    'energy': 'Запасённая энергия',
}

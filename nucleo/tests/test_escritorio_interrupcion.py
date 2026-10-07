from azul.escritorio.interrupcion import VigiaDeInterrupcion


def test_echo_of_azul_is_learned_and_ignored():
    vigia = VigiaDeInterrupcion()

    avisos = [vigia.hay_voz_encima(0.08, 0.2) for _ in range(50)]

    assert not any(avisos)
    assert 0.35 < vigia.acople < 0.45


def test_a_voice_well_above_the_echo_is_noticed_after_two_blocks():
    vigia = VigiaDeInterrupcion()
    for _ in range(30):
        vigia.hay_voz_encima(0.08, 0.2)

    assert not vigia.hay_voz_encima(0.5, 0.2)
    assert vigia.hay_voz_encima(0.5, 0.2)


def test_when_azul_is_silent_any_clear_voice_counts():
    vigia = VigiaDeInterrupcion()

    assert not vigia.hay_voz_encima(0.05, 0.0)
    assert vigia.hay_voz_encima(0.05, 0.0)
    vigia.reiniciar()
    assert not vigia.hay_voz_encima(0.005, 0.0)

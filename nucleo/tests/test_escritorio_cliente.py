import json
from datetime import datetime, time

from azul.escritorio.cliente import TONO_FIN, TONO_INICIO, ClienteEscritorio
from tests.test_escritorio_deteccion import SILENCIO, VOZ


class FakeParlante:
    def __init__(self):
        self.sonando = False
        self.mp3 = []
        self.tonos = []
        self.por_sonar = []  # lo que sigue en el parlante: detener() lo vacía, como el real
        self.detenido = 0
        self.nivel = 0.0
        self.pausado = False

    def pausar(self):
        self.pausado = True

    def reanudar(self):
        self.pausado = False

    def reproducir_mp3(self, mp3):
        self.mp3.append(mp3)
        self.sonando = True

    def tono(self, frecuencia=880, milisegundos=150):
        self.tonos.append((frecuencia, milisegundos))
        self.por_sonar.append((frecuencia, milisegundos))
        self.sonando = True

    def detener(self):
        self.detenido += 1
        self.por_sonar.clear()
        self.sonando = False


def crear(oye_azul=True, hora=datetime(2026, 10, 5, 10, 0)):
    enviados = []
    parlante = FakeParlante()
    cliente = ClienteEscritorio(
        parlante,
        enviados.append,
        oye_azul=oye_azul,
        desde=time(7, 0),
        hasta=time(22, 0),
        programar=lambda segundos, accion: accion(),  # sin esperas en las pruebas
        reloj=lambda: hora,
    )
    return cliente, parlante, enviados


def tipos(enviados):
    return [json.loads(m)["tipo"] if isinstance(m, str) else "audio" for m in enviados]


def evento(**datos):
    return json.dumps(datos)


def test_shortcut_starts_a_conversation_and_streams_the_microphone():
    cliente, parlante, enviados = crear()

    cliente.atajo()
    cliente.bloque_de_microfono(VOZ)

    assert parlante.por_sonar == [TONO_INICIO]  # el tono suena, no se borra al empezar
    assert tipos(enviados) == ["hablar_inicio", "audio"]
    assert cliente.escuchando and cliente.en_conversacion


def test_full_conversation_turn_then_listens_again():
    cliente, parlante, enviados = crear()
    cliente.atajo()

    cliente.mensaje(evento(tipo="turno"))
    cliente.mensaje(evento(tipo="escucha_terminada"))
    cliente.mensaje(evento(tipo="texto", texto="Son las diez."))
    cliente.mensaje(b"mp3-de-una-frase")
    cliente.mensaje(evento(tipo="fin"))

    assert parlante.mp3 == [b"mp3-de-una-frase"]
    assert tipos(enviados) == ["hablar_inicio", "hablar_fin"]  # aún suena: no escucha

    parlante.sonando = False
    cliente.termino_el_audio()

    assert tipos(enviados)[-1] == "hablar_inicio"  # segundo turno, sin tocar nada
    assert cliente.escuchando


def test_silence_after_an_answer_ends_the_conversation_with_a_tone():
    cliente, parlante, _ = crear()
    cliente.atajo()
    cliente.mensaje(evento(tipo="turno"))
    cliente.mensaje(b"mp3")
    parlante.sonando = False
    cliente.mensaje(evento(tipo="fin"))  # turno 1 completo; empieza el turno 2
    cliente.mensaje(evento(tipo="nada_escuchado"))

    assert not cliente.en_conversacion
    assert parlante.tonos[-1] == TONO_FIN


def test_shortcut_while_azul_speaks_stops_it():
    cliente, parlante, enviados = crear()
    cliente.atajo()
    cliente.mensaje(evento(tipo="turno"))
    cliente.mensaje(evento(tipo="escucha_terminada"))
    cliente.mensaje(b"mp3")

    cliente.atajo()

    assert tipos(enviados)[-1] == "parar"
    assert not parlante.sonando
    assert not cliente.en_conversacion


def test_audio_from_an_interrupted_turn_is_ignored():
    cliente, parlante, _ = crear()
    cliente.atajo()
    cliente.mensaje(evento(tipo="turno"))
    cliente.mensaje(evento(tipo="escucha_terminada"))
    cliente.parar()

    cliente.mensaje(b"mp3-que-llega-tarde")

    assert parlante.mp3 == []


def voz_y_silencio(cliente, bloques_voz=5, bloques_silencio=12):
    for _ in range(5):
        cliente.bloque_de_microfono(SILENCIO)
    for _ in range(bloques_voz):
        cliente.bloque_de_microfono(VOZ)
    for _ in range(bloques_silencio):
        cliente.bloque_de_microfono(SILENCIO)


def test_wake_word_fragment_is_sent_within_schedule():
    cliente, _, enviados = crear()

    voz_y_silencio(cliente)

    assert tipos(enviados)[0] == "activacion_inicio"
    assert tipos(enviados)[-1] == "activacion_fin"
    assert cliente.esperando_fragmento

    cliente.mensaje(evento(tipo="ignorado"))
    cliente.mensaje(evento(tipo="fin"))
    assert not cliente.esperando_fragmento


def test_wake_word_alone_starts_a_conversation():
    cliente, parlante, enviados = crear()
    voz_y_silencio(cliente)

    cliente.mensaje(evento(tipo="activado"))

    assert parlante.por_sonar == [TONO_INICIO]  # el tono suena, no se borra al empezar
    assert tipos(enviados)[-1] == "hablar_inicio"
    assert cliente.en_conversacion


def test_silence_after_the_wake_word_ends_with_a_tone():
    # Si tras "Oye Azul" no preguntas nada, Azul avisa que dejó de escuchar.
    cliente, parlante, _ = crear()
    voz_y_silencio(cliente)
    cliente.mensaje(evento(tipo="activado"))
    cliente.mensaje(evento(tipo="turno"))

    cliente.mensaje(evento(tipo="nada_escuchado"))

    assert parlante.tonos[-1] == TONO_FIN
    assert not cliente.en_conversacion


def test_no_wake_word_listening_outside_schedule_or_when_disabled():
    noche, _, enviados_noche = crear(hora=datetime(2026, 10, 5, 23, 30))
    voz_y_silencio(noche)
    apagado, _, enviados_apagado = crear(oye_azul=False)
    voz_y_silencio(apagado)

    assert enviados_noche == []
    assert enviados_apagado == []


def test_shortcut_still_works_outside_schedule():
    cliente, _, enviados = crear(hora=datetime(2026, 10, 5, 23, 30))

    cliente.atajo()

    assert tipos(enviados) == ["hablar_inicio"]


def test_fragment_ends_as_soon_as_azul_says_the_sentence_ended():
    cliente, _, enviados = crear()
    for _ in range(5):
        cliente.bloque_de_microfono(SILENCIO)
    for _ in range(4):
        cliente.bloque_de_microfono(VOZ)  # sigue "sonando" (ruido): el detector no corta

    cliente.mensaje(evento(tipo="escucha_terminada"))
    enviados_antes = len(enviados)
    cliente.bloque_de_microfono(VOZ)

    assert tipos(enviados)[-1] == "activacion_fin"
    assert len(enviados) == enviados_antes  # ya no envía más audio de ese fragmento


def test_wake_word_alone_keeps_listening_despite_the_stop_ack():
    # Tras "Oye Azul" el cliente empieza un turno; el núcleo confirma la interrupción
    # del turno anterior con "parado". Eso no debe cortar la conversación (era el fallo).
    cliente, _, enviados = crear()
    voz_y_silencio(cliente)
    cliente.mensaje(evento(tipo="activado"))

    cliente.mensaje(evento(tipo="parado"))
    cliente.bloque_de_microfono(VOZ)

    assert cliente.escuchando and cliente.en_conversacion
    assert tipos(enviados)[-1] == "audio"


def test_noise_without_words_raises_the_detection_threshold():
    cliente, _, enviados = crear()
    ruido = bloque_de(900)  # ~0,027: más fuerte que el umbral inicial
    for _ in range(40):
        cliente.bloque_de_microfono(ruido)
    assert tipos(enviados)[0] == "activacion_inicio"

    cliente.mensaje(evento(tipo="escucha_terminada"))
    cliente.mensaje(evento(tipo="ignorado", con_palabras=False))
    cliente.mensaje(evento(tipo="fin"))
    enviados.clear()
    for _ in range(40):
        cliente.bloque_de_microfono(ruido)

    assert enviados == []  # el mismo ruido ya no abre fragmentos


def test_other_peoples_speech_does_not_raise_the_threshold():
    cliente, _, enviados = crear()
    voz_y_silencio(cliente)
    cliente.mensaje(evento(tipo="ignorado", con_palabras=True))
    cliente.mensaje(evento(tipo="fin"))
    enviados.clear()

    voz_y_silencio(cliente)

    assert tipos(enviados)[0] == "activacion_inicio"  # sigue oyendo voz a ese volumen


def bloque_de(amplitud):
    from tests.test_escritorio_deteccion import bloque

    return bloque(amplitud)


class FakeReconocedor:
    """Reconoce "Oye Azul" al recibir su tercer bloque de audio."""

    def __init__(self, al_bloque=3, al_cerrar=False):
        self.al_bloque = al_bloque
        self.al_cerrar = al_cerrar
        self.bloques = 0
        self.reinicios = 0

    def cerrar(self):
        return self.al_cerrar

    def reiniciar(self):
        self.reinicios += 1
        self.bloques = 0

    def escuchar(self, bloque):
        self.bloques += 1
        return self.bloques == self.al_bloque


def crear_local(reconocedor, hora=datetime(2026, 10, 5, 3, 0)):
    enviados = []
    parlante = FakeParlante()
    cliente = ClienteEscritorio(
        parlante,
        enviados.append,
        oye_azul=True,
        desde=time(0, 0),
        hasta=time(0, 0),
        programar=lambda segundos, accion: accion(),
        reloj=lambda: hora,
        reconocedor=reconocedor,
    )
    return cliente, parlante, enviados


def test_local_wake_word_opens_a_turn_with_the_recent_audio_and_a_tone():
    cliente, parlante, enviados = crear_local(FakeReconocedor(al_bloque=3))

    voz_y_silencio(cliente, bloques_voz=6)

    tipos_enviados = tipos(enviados)
    # Nada sale del portátil hasta oír "Oye Azul": luego el turno con el audio del llamado.
    assert tipos_enviados[0] == "hablar_inicio"
    assert "activacion_inicio" not in tipos_enviados
    assert tipos_enviados.count("audio") >= 3
    assert cliente.escuchando and cliente.en_conversacion
    assert parlante.por_sonar == [TONO_INICIO]


def test_speech_without_the_wake_word_never_leaves_the_laptop():
    cliente, _, enviados = crear_local(FakeReconocedor(al_bloque=999))

    voz_y_silencio(cliente, bloques_voz=6)
    voz_y_silencio(cliente, bloques_voz=6)

    assert enviados == []
    assert not cliente.en_conversacion


def test_wake_word_found_only_when_the_sentence_ends_still_opens_the_turn():
    # "Oye Azul, ¿qué hora es?" de corrido: a veces solo la lectura final lo reconoce,
    # y entonces se envía la frase entera para no perder la pregunta.
    cliente, _, enviados = crear_local(FakeReconocedor(al_bloque=999, al_cerrar=True))

    voz_y_silencio(cliente, bloques_voz=6)

    assert tipos(enviados)[0] == "hablar_inicio"
    assert tipos(enviados).count("audio") >= 6
    assert cliente.escuchando


def azul_hablando(nivel=0.2):
    # Aquí las esperas no se cumplen solas: la pausa dura hasta que llegue el veredicto.
    enviados = []
    parlante = FakeParlante()
    cliente = ClienteEscritorio(
        parlante,
        enviados.append,
        oye_azul=True,
        desde=time(7, 0),
        hasta=time(22, 0),
        programar=lambda segundos, accion: None,
        reloj=lambda: datetime(2026, 10, 5, 10, 0),
    )
    cliente.atajo()
    cliente.mensaje(evento(tipo="turno"))
    cliente.mensaje(evento(tipo="escucha_terminada"))
    cliente.mensaje(b"mp3")
    parlante.nivel = nivel
    enviados.clear()
    return cliente, parlante, enviados


def test_azul_echo_alone_does_not_interrupt():
    cliente, parlante, enviados = azul_hablando(nivel=0.2)

    for _ in range(30):
        cliente.bloque_de_microfono(bloque_de(2000))  # ~0,06: su propio eco

    assert enviados == []
    assert not parlante.pausado


def test_voice_over_azul_pauses_her_and_sends_clean_audio_to_verify():
    cliente, parlante, enviados = azul_hablando(nivel=0.2)
    for _ in range(10):
        cliente.bloque_de_microfono(bloque_de(2000))

    for _ in range(40):
        cliente.bloque_de_microfono(bloque_de(16000))  # ~0,49: alguien le habla encima

    assert parlante.pausado
    assert tipos(enviados)[0] == "interrupcion_inicio"
    assert tipos(enviados).count("audio") >= 36
    assert "interrupcion_fin" in tipos(enviados)


def test_users_voice_takes_over_and_others_let_azul_continue():
    cliente, parlante, _ = azul_hablando(nivel=0.2)
    for _ in range(3):
        cliente.bloque_de_microfono(bloque_de(16000))

    cliente.mensaje(evento(tipo="no_eres_tu"))
    assert not parlante.pausado and cliente.respondiendo is not None

    for _ in range(3):
        cliente.bloque_de_microfono(bloque_de(16000))
    cliente.mensaje(evento(tipo="interrumpido"))

    assert cliente.escuchando and cliente.en_conversacion
    assert parlante.detenido >= 1


def test_when_another_device_answers_the_laptop_stays_quiet():
    cliente, parlante, _ = crear()
    cliente.atajo()
    cliente.mensaje(evento(tipo="turno"))
    tonos_antes = list(parlante.tonos)

    cliente.mensaje(evento(tipo="otro_dispositivo"))

    assert not cliente.escuchando and not cliente.respondiendo
    assert parlante.tonos == tonos_antes  # ni siquiera el tono de cierre

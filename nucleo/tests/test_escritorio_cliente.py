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

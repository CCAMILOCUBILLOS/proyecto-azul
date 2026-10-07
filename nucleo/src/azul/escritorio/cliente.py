"""Cliente de voz de escritorio: estados, atajo, "Oye Azul" y conexión (ADR 0028).

Usa el mismo protocolo que la app (/api/voz). La lógica no depende del
hardware: recibe bloques de micrófono, mensajes del núcleo y avisos del
parlante, y produce mensajes de salida. Así se puede probar sin audio real.
"""

import json
import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime, time
from typing import Any, Protocol

from azul.escritorio.deteccion import DetectorDeVoz, volumen
from azul.escritorio.horario import dentro_del_horario
from azul.escritorio.interrupcion import VigiaDeInterrupcion

log = logging.getLogger(__name__)

PAUSA_ANTES_DE_ESCUCHAR = 0.35  # que no se cuele el final de la voz de Azul
TONO_INICIO = (880, 150)
TONO_FIN = (520, 180)
# Al oír "Oye Azul" en local se envía también el audio reciente de esa frase (hasta
# 6 s): así no se pierde la pregunta de "Oye Azul, ¿qué hora es?" dicho de corrido.
BLOQUES_DEL_LLAMADO = 60
# Interrumpir con la voz (ADR 0036): hasta 3,6 s de audio limpio para verificar quién
# habla (el núcleo decide con 2,2 s y, si duda, con 3,5 s).
BLOQUES_PARA_VERIFICAR = 36
SEGUNDOS_ESPERANDO_VEREDICTO = 5.0


class ParlanteLike(Protocol):
    @property
    def sonando(self) -> bool: ...

    @property
    def nivel(self) -> float: ...

    def pausar(self) -> None: ...

    def reanudar(self) -> None: ...

    def reproducir_mp3(self, mp3: bytes) -> None: ...

    def tono(self, frecuencia: float = 880, milisegundos: int = 150) -> None: ...

    def detener(self) -> None: ...


class ReconocedorLike(Protocol):
    def reiniciar(self) -> None: ...

    def escuchar(self, bloque: bytes) -> bool: ...

    def cerrar(self) -> bool: ...


class ClienteEscritorio:
    def __init__(
        self,
        parlante: ParlanteLike,
        enviar: Callable[[str | bytes], None],
        *,
        oye_azul: bool,
        desde: time,
        hasta: time,
        programar: Callable[[float, Callable[[], None]], None],
        reloj: Callable[[], datetime] = datetime.now,
        reconocedor: ReconocedorLike | None = None,
    ) -> None:
        self._parlante = parlante
        self._enviar = enviar
        self._oye_azul = oye_azul
        self._desde = desde
        self._hasta = hasta
        self._programar = programar
        self._reloj = reloj
        # Con reconocedor local (ADR 0035), "Oye Azul" se reconoce aquí y no se envía
        # nada hasta oírlo; sin él, cada fragmento con voz lo revisa el núcleo (Deepgram).
        self._reconocedor = reconocedor
        self._oido: deque[bytes] = deque(maxlen=BLOQUES_DEL_LLAMADO)
        self._vigia = VigiaDeInterrupcion()
        self._interrumpiendo = False
        self._bloques_interrupcion = 0
        self._interrupcion_disponible = True
        if reconocedor is not None:
            self._detector = DetectorDeVoz(
                empezar=self._empezar_local, audio=self._oir, terminar=self._terminar_local
            )
        else:
            self._detector = DetectorDeVoz(
                empezar=self._empezar_fragmento,
                audio=self._enviar,
                terminar=self._terminar_fragmento,
            )
        self.escuchando = False
        self.respondiendo = False
        self.esperando_fragmento = False
        self.en_conversacion = False
        self._turno_con_respuesta = False
        self._turnos = 0
        self._aceptar_audio = False

    # --- Entradas ---

    def atajo(self) -> None:
        """Atajo de teclado: empieza a conversar, envía ya, o calla a Azul."""
        if self.escuchando:
            self._dejar_de_escuchar()
        elif self.respondiendo or self._parlante.sonando:
            self.parar()
        else:
            log.info("Atajo: escuchando")
            self._iniciar_conversacion()
            self._avisar_que_escucha()

    def parar(self) -> None:
        self._enviar_json({"tipo": "parar"})
        self._parlante.detener()
        self._aceptar_audio = False
        self.respondiendo = False
        self._terminar_conversacion()

    def bloque_de_microfono(self, bloque: bytes) -> None:
        if self.escuchando:
            self._enviar(bloque)
        elif self._interrumpiendo:
            self._enviar(bloque)
            self._bloques_interrupcion += 1
            if self._bloques_interrupcion == BLOQUES_PARA_VERIFICAR:
                self._enviar_json({"tipo": "interrupcion_fin"})
        elif self._interrupcion_disponible and (self.respondiendo or self._parlante.sonando):
            nivel_azul = self._parlante.nivel if self._parlante.sonando else 0.0
            if self._vigia.hay_voz_encima(volumen(bloque), nivel_azul):
                self._empezar_interrupcion()
        elif self._oye_azul:
            self._detector.agregar(bloque, puede_empezar=self._puede_activarse())

    def mensaje(self, mensaje: str | bytes) -> None:
        if isinstance(mensaje, bytes):
            if self._aceptar_audio:
                self._turno_con_respuesta = True
                self._parlante.reproducir_mp3(mensaje)
            return
        evento: dict[str, Any] = json.loads(mensaje)
        match evento.get("tipo"):
            case "turno":
                self._aceptar_audio = True
            case "escucha_terminada":
                if self.escuchando:
                    self._dejar_de_escuchar()
                elif self._detector.en_fragmento:
                    # Azul ya sabe que terminaste la frase: no hace falta esperar al silencio.
                    self._detector.reiniciar()
                    self._terminar_fragmento()
            case "activado":
                # Dijeron solo "Oye Azul": tono y a escuchar la pregunta.
                log.info("Oye Azul: escuchando la pregunta")
                self.esperando_fragmento = False
                self._iniciar_conversacion()
                self._avisar_que_escucha()
            case "texto":
                self.esperando_fragmento = False
                self.respondiendo = True
                self._turno_con_respuesta = True
            case "nada_escuchado":
                # Silencio: Azul deja de escuchar y lo avisa con el tono de cierre, también
                # si no alcanzaste a preguntar nada (antes se apagaba sin avisar).
                log.info("No se oyó nada: fin de la conversación")
                self.escuchando = False
                self.respondiendo = False
                if self.en_conversacion:
                    self._parlante.tono(*TONO_FIN)
                self._terminar_conversacion()
            case "interrumpido":
                # Era la voz del usuario: Azul se calla y lo que él dice es el nuevo mensaje.
                log.info("Interrumpida por la voz del usuario")
                self._interrumpiendo = False
                self._parlante.detener()
                self._aceptar_audio = False
                self._turno_con_respuesta = False
                self.respondiendo = False
                self.en_conversacion = True
                self.escuchando = True
            case "no_eres_tu" | "interrupcion_no_disponible":
                if evento.get("tipo") == "interrupcion_no_disponible":
                    self._interrupcion_disponible = False
                self._seguir_hablando()
            case "parado":
                # Si ya estamos escuchando, es la confirmación de que nuestro propio turno
                # nuevo interrumpió al anterior: no significa que el usuario pidió parar.
                if not self.escuchando:
                    self.respondiendo = False
                    self._terminar_conversacion()
            case "ignorado":
                # Si no tenía ni una palabra era ruido: el detector aprende su nivel. Si tenía
                # palabras (otra conversación), no, para no dejar de oír al usuario.
                if not evento.get("con_palabras", True):
                    self._detector.aprender_ruido()
            case "error":
                log.warning("Azul informó un error: %s", evento.get("mensaje"))
                self.respondiendo = False
                self._terminar_conversacion()
            case "fin":
                # Si el usuario enseña su voz después, en la próxima respuesta se vuelve a probar.
                self._interrupcion_disponible = True
                self.esperando_fragmento = False
                self.respondiendo = False
                if self._turno_con_respuesta:
                    log.info("Azul respondió")
                    self._turnos += 1
                self._turno_con_respuesta = False
                self._continuar()
            case _:
                pass

    def termino_el_audio(self) -> None:
        """El parlante terminó de hablar: si hay conversación, se vuelve a escuchar."""
        self._continuar()

    # --- Interno ---

    def _iniciar_conversacion(self) -> None:
        self.en_conversacion = True
        self._turnos = 0
        self._empezar_turno()

    def _terminar_conversacion(self) -> None:
        self.en_conversacion = False
        self.escuchando = False

    def _avisar_que_escucha(self) -> None:
        # Va después de empezar el turno: empezarlo vacía el parlante, y el tono se perdía.
        self._parlante.tono(*TONO_INICIO)

    def _empezar_turno(self) -> None:
        self._parlante.detener()
        self._detector.reiniciar()
        self._aceptar_audio = False
        self._turno_con_respuesta = False
        self._enviar_json({"tipo": "hablar_inicio"})
        self.escuchando = True

    def _dejar_de_escuchar(self) -> None:
        self.escuchando = False
        self.respondiendo = True
        self._enviar_json({"tipo": "hablar_fin"})

    def _continuar(self) -> None:
        if not self.en_conversacion:
            return

        def intentar() -> None:
            if self.en_conversacion and self._libre():
                self._empezar_turno()

        self._programar(PAUSA_ANTES_DE_ESCUCHAR, intentar)

    def _libre(self) -> bool:
        return not (
            self.escuchando
            or self.respondiendo
            or self.esperando_fragmento
            or self._parlante.sonando
        )

    def _puede_activarse(self) -> bool:
        if not self._libre() or self.en_conversacion:
            return False
        return dentro_del_horario(self._reloj().time(), self._desde, self._hasta)

    # --- Interrumpir con la voz (ADR 0036) ---

    def _empezar_interrupcion(self) -> None:
        # Pausa corta: así el núcleo verifica la voz sin el eco de Azul encima.
        self._interrumpiendo = True
        self._bloques_interrupcion = 0
        self._parlante.pausar()
        self._enviar_json({"tipo": "interrupcion_inicio"})
        self._programar(SEGUNDOS_ESPERANDO_VEREDICTO, self._sin_veredicto)

    def _seguir_hablando(self) -> None:
        if self._interrumpiendo and self._bloques_interrupcion < BLOQUES_PARA_VERIFICAR:
            self._enviar_json({"tipo": "interrupcion_fin"})
        self._interrumpiendo = False
        self._vigia.reiniciar()
        self._parlante.reanudar()

    def _sin_veredicto(self) -> None:
        if self._interrumpiendo:
            self._seguir_hablando()

    # --- "Oye Azul" local ---

    def _empezar_local(self, previos: list[bytes]) -> None:
        assert self._reconocedor is not None
        self._reconocedor.reiniciar()
        self._oido.clear()
        for bloque in previos:
            if self._oir(bloque):
                return

    def _oir(self, bloque: bytes) -> bool:
        assert self._reconocedor is not None
        if self.escuchando:
            return True
        self._oido.append(bloque)
        if not self._reconocedor.escuchar(bloque):
            return False
        self._detector.reiniciar()
        self._llamado()
        return True

    def _llamado(self) -> None:
        log.info("Oye Azul (reconocido en el portátil)")
        self._iniciar_conversacion()
        for previo in self._oido:
            self._enviar(previo)
        self._oido.clear()
        self._avisar_que_escucha()

    def _terminar_local(self) -> None:
        assert self._reconocedor is not None
        # Al terminar la frase, la lectura completa a veces reconoce lo que la parcial no.
        if not self.escuchando and self._reconocedor.cerrar():
            self._llamado()
        self._reconocedor.reiniciar()
        self._oido.clear()

    # --- "Oye Azul" por el núcleo (sin reconocedor local) ---

    def _empezar_fragmento(self, previos: list[bytes]) -> None:
        self.esperando_fragmento = True
        self._enviar_json({"tipo": "activacion_inicio"})
        for bloque in previos:
            self._enviar(bloque)

    def _terminar_fragmento(self) -> None:
        self._enviar_json({"tipo": "activacion_fin"})

    def _enviar_json(self, datos: dict[str, Any]) -> None:
        self._enviar(json.dumps(datos))

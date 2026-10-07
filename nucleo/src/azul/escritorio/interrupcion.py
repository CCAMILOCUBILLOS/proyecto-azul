"""¿Alguien le habla encima a Azul? Para el portátil, que no cancela el eco (ADR 0036).

En el portátil, la voz de Azul sale por los parlantes y vuelve a entrar por el
micrófono. El vigía aprende cuánto de lo que suena "regresa" al micrófono (el
acople) y avisa solo cuando el micrófono oye bastante más de lo que explicaría
el eco: entonces Azul hace una pausa corta y el núcleo verifica, con audio
limpio, si quien habla es el usuario.
"""

# El micrófono debe superar al eco esperado en este factor para sospechar de una voz.
VECES_SOBRE_EL_ECO = 2.5
NIVEL_MINIMO = 0.01
BLOQUES_SEGUIDOS = 2
ACOPLE_INICIAL = 0.3
# El acople cambia poco: se aprende despacio, y no con lo que ya parece una voz encima.
APRENDIZAJE = 0.05


class VigiaDeInterrupcion:
    def __init__(self) -> None:
        self.acople = ACOPLE_INICIAL
        self._seguidos = 0

    def reiniciar(self) -> None:
        self._seguidos = 0

    def hay_voz_encima(self, nivel_microfono: float, nivel_azul: float) -> bool:
        """Un bloque de 0,1 s: niveles RMS (0 a 1) del micrófono y de lo que suena."""
        eco_esperado = self.acople * nivel_azul
        sospecha = nivel_microfono > max(NIVEL_MINIMO, VECES_SOBRE_EL_ECO * eco_esperado)
        if nivel_azul > NIVEL_MINIMO and not sospecha:
            proporcion = min(1.5, nivel_microfono / nivel_azul)
            self.acople += (proporcion - self.acople) * APRENDIZAJE
        self._seguidos = self._seguidos + 1 if sospecha else 0
        return self._seguidos >= BLOQUES_SEGUIDOS

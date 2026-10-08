"""Órdenes directas: lo que Azul ya sabe hacer, sin gastar en Claude (ADR 0042).

Antes de ir al cerebro, Azul mira si el mensaje es una orden conocida para uno de
los programas del "ecosistema" (Red Nacional, el itinerario de correos). Si lo es,
la ejecuta directo y responde con una frase fija: cero costo de Claude.

- Catálogo: órdenes que empiezan con la acción ("corre el agendamiento", "haz el
  cargue") o preguntas fijas ("¿cuántas órdenes hay pendientes?", "¿cómo va?"). Si la
  frase trae algo más que la orden y una fecha, va a Claude: así nada se ejecuta por
  confusión ("¿ya corriste el agendamiento?" no lo vuelve a correr).
- Atajos aprendidos: cuando Claude resuelve una orden corta con un solo programa
  conocido, la frase queda guardada y la próxima vez se hace directo.
- El cargue real (crea órdenes en Biofile) pide un "sí" antes; esa confirmación
  tampoco gasta.
"""

import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from azul.core.ports import RedNacional, RedNacionalError

log = logging.getLogger(__name__)

MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
_MES = "(" + "|".join(MESES) + ")"
MAX_PALABRAS_ATAJO = 9
SI = {
    "si",
    "dale",
    "hazlo",
    "confirmo",
    "si hazlo",
    "si claro",
    "de una",
    "si dale",
    "claro",
    "ok",
}
NO = {"no", "cancela", "mejor no", "no lo hagas", "cancelalo", "espera"}

# Lo que se puede volver atajo: programas con respuesta fija y sin riesgo de repetir.
_PROCESOS_REPETIBLES = {
    "agendar",
    "agendar_simulacion",
    "correos",
    "simulacion",
    "verificar",
    "base",
    "sincronizar_seguimiento",
    "control_sync",
    "reporte",
}
_SECCIONES_CON_RESPUESTA = {"resumen", "progreso"}

HABLADO = {
    "agendar": "el agendamiento",
    "agendar_simulacion": "la simulación del agendamiento",
    "correos": "la lectura de correos de red nacional",
    "simulacion": "la simulación del cargue",
    "cargue": "el cargue real",
    "verificar": "la verificación del catálogo",
    "base": "la descarga de la base de Biofile",
    "sincronizar_seguimiento": "la actualización del seguimiento",
    "control_sync": "el paso de órdenes a CONTROL RED NACIONAL",
    "reporte": "el reporte de red nacional",
}
_CON_FECHAS = {"agendar", "agendar_simulacion", "correos", "base", "sincronizar_seguimiento"}


class MemoriaDeAtajos(Protocol):
    async def atajo_buscar(self, frase: str) -> tuple[str, dict[str, Any]] | None: ...

    async def atajo_guardar(
        self, frase: str, herramienta: str, entrada: dict[str, Any]
    ) -> None: ...


@dataclass(frozen=True)
class Orden:
    nombre: str  # proceso de Red Nacional, "consulta:<sección>" o "itinerario"
    patron: re.Pattern[str]
    fechas: bool = False


_V = r"(?:haz|hacer|corre|correr|ejecuta|lanza|inicia|arranca|realiza|genera|crea|prepara)"


def _orden(nombre: str, patron: str, fechas: bool = False) -> Orden:
    return Orden(nombre, re.compile(rf"^(?:{patron})"), fechas)


# Orden importa: lo más específico primero (las simulaciones antes que lo real).
CATALOGO = (
    _orden(
        "agendar_simulacion",
        rf"simula (?:el |los )?agendamientos?|{_V} (?:la )?simulacion del? agendamiento",
        fechas=True,
    ),
    _orden(
        "agendar",
        rf"{_V} (?:los |el )?agendamientos?(?: de red nacional)?|agenda(?:r)? red nacional"
        rf"|{_V} (?:los )?borradores (?:de red nacional|para las ips|de las ips)",
        fechas=True,
    ),
    _orden(
        "correos",
        rf"(?:{_V}|lee|revisa) (?:la lectura de )?(?:los )?correos de red nacional"
        rf"|{_V} el excel de red nacional",
        fechas=True,
    ),
    _orden("simulacion", rf"simula (?:el )?cargue|{_V} la simulacion del? cargue"),
    _orden(
        "cargue",
        rf"{_V} el cargue(?: real)?|carga (?:las )?ordenes(?: pendientes)?(?: en biofile)?"
        rf"|crea las ordenes(?: pendientes)?(?: en biofile)?",
    ),
    _orden("verificar", r"(?:verifica|revisa) el catalogo(?: contra biofile)?"),
    _orden("base", r"(?:baja|descarga|actualiza) la base(?: de biofile| de ordenes)?", True),
    _orden(
        "sincronizar_seguimiento",
        r"(?:actualiza|sincroniza) el seguimiento(?: de red nacional)?",
        fechas=True,
    ),
    _orden(
        "control_sync",
        r"(?:sincroniza|actualiza) (?:el )?control(?: red nacional)?"
        r"|pasa las ordenes al control(?: red nacional)?",
    ),
    _orden("reporte", rf"(?:{_V}|saca) el reporte(?: de red nacional)?"),
    _orden("detener", r"(?:deten|detener|cancela|frena) el proceso"),
    _orden(
        "consulta:resumen",
        r"cuantas ordenes (?:hay |quedan )?pendientes(?: por cargar)?(?: en red nacional)?"
        r"|como (?:esta|va) red nacional|resumen de red nacional"
        r"|que hay pendiente por cargar",
    ),
    _orden(
        "consulta:progreso",
        r"como va(?: el proceso| eso| el agendamiento| el cargue| la simulacion)?$"
        r"|ya termino(?: el proceso)?$|en que va(?: el proceso)?$",
    ),
    _orden(
        "itinerario",
        r"(?:que tengo pendiente(?: hoy| en el correo| en los correos)?"
        r"|que es lo mas urgente(?: del correo)?|cual es mi itinerario"
        r"|que hay urgente en el correo)$",
    ),
)


class RecepcionDeOrdenes:
    def __init__(
        self,
        red_nacional: RedNacional | None,
        atajos: MemoriaDeAtajos,
        itinerario: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._red = red_nacional
        self._atajos = atajos
        self._itinerario = itinerario
        self._now = now
        self._por_confirmar: Callable[[], Awaitable[str]] | None = None

    async def atender(self, texto: str) -> str | None:
        """La respuesta si es una orden directa; None si le toca a Claude."""
        limpio = normalizar(texto)
        pendiente, self._por_confirmar = self._por_confirmar, None
        if pendiente is not None:
            if limpio in SI:
                return await pendiente()
            if limpio in NO:
                return "Listo, no lo hago."
        orden = self._reconocer(limpio)
        if orden is not None:
            nombre, desde, hasta = orden
            log.info("Orden directa: %s", nombre)
            return await self._ejecutar(nombre, desde, hasta)
        atajo = await self._atajos.atajo_buscar(limpio)
        if atajo is not None:
            herramienta, entrada = atajo
            log.info("Atajo aprendido: %s", herramienta)
            return await self._repetir(herramienta, entrada)
        return None

    def reconoce(self, texto: str) -> bool:
        """¿Empieza como una orden del catálogo? (para no precalentar a Claude en vano)"""
        limpio = normalizar(texto)
        return any(orden.patron.match(limpio) for orden in CATALOGO)

    async def aprender(self, texto: str, llamadas: list[tuple[str, dict[str, Any]]]) -> None:
        """Si Claude resolvió una orden corta con un solo programa conocido, se guarda."""
        limpio = normalizar(texto)
        if len(llamadas) != 1 or not limpio or len(limpio.split()) > MAX_PALABRAS_ATAJO:
            return
        if self._reconocer(limpio) is not None:
            return
        herramienta, entrada = llamadas[0]
        if not _repetible(herramienta, entrada):
            return
        plantilla = _con_fechas_relativas(entrada, self._hoy())
        if plantilla is None:
            return
        await self._atajos.atajo_guardar(limpio, herramienta, plantilla)
        log.info("Atajo aprendido: %s", herramienta)

    # --- Reconocer ---

    def _reconocer(self, limpio: str) -> tuple[str, date, date] | None:
        hoy = self._hoy()
        for orden in CATALOGO:
            encontrado = orden.patron.match(limpio)
            if not encontrado:
                continue
            programa = self._itinerario if orden.nombre == "itinerario" else self._red
            if programa is None:
                return None
            resto = limpio[encontrado.end() :].strip()
            sin_resto = None if resto else (hoy, hoy)
            rango = fechas(resto, hoy) if orden.fechas else sin_resto
            if rango is None:
                return None  # sobra algo que no es una fecha: mejor que lo entienda Claude
            return orden.nombre, rango[0], rango[1]
        return None

    # --- Ejecutar y responder ---

    async def _ejecutar(self, nombre: str, desde: date, hasta: date) -> str:
        if nombre == "itinerario":
            assert self._itinerario is not None
            return _itinerario_hablado(await self._itinerario())
        if nombre.startswith("consulta:"):
            return await self._consultar(nombre.removeprefix("consulta:"))
        if nombre == "cargue":
            return await self._preparar_cargue()
        datos = {}
        if nombre in _CON_FECHAS:
            datos = {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
        return await self._lanzar(nombre, datos)

    async def _repetir(self, herramienta: str, plantilla: dict[str, Any]) -> str:
        entrada = _con_fechas_de_hoy(plantilla, self._hoy())
        if herramienta == "correo_itinerario" and self._itinerario is not None:
            return _itinerario_hablado(await self._itinerario())
        if herramienta == "red_nacional_consultar":
            return await self._consultar(str(entrada.get("seccion")))
        operacion = str(entrada.get("operacion"))
        datos = {k: v for k, v in entrada.items() if k != "operacion"}
        return await self._lanzar(operacion, datos)

    async def _lanzar(self, operacion: str, datos: dict[str, Any]) -> str:
        assert self._red is not None
        try:
            resultado = await self._red.ejecutar(operacion, datos)
        except RedNacionalError as error:
            return str(error)
        if operacion == "detener":
            return "Listo, detuve el proceso." if _ok(resultado) else _motivo(resultado)
        if not _ok(resultado):
            return f"No pude lanzar {HABLADO.get(operacion, operacion)}: {_motivo(resultado)}"
        rango = _rango_hablado(datos, self._hoy())
        return (
            f"Listo, lancé {HABLADO.get(operacion, operacion)}{rango}. Pregúntame «¿cómo va?» "
            "para saber el avance."
        )

    async def _consultar(self, seccion: str) -> str:
        assert self._red is not None
        try:
            datos = await self._red.consultar(seccion, {})
        except RedNacionalError as error:
            return str(error)
        if seccion == "resumen":
            return _resumen_hablado(datos)
        return _progreso_hablado(datos)

    async def _preparar_cargue(self) -> str:
        assert self._red is not None
        try:
            resumen = await self._red.consultar("resumen", {})
        except RedNacionalError as error:
            return str(error)
        pendientes = int(resumen.get("pendientes") or 0) if isinstance(resumen, dict) else 0
        if not pendientes:
            return "No hay órdenes pendientes por crear, así que no hay nada que cargar."

        async def cargar() -> str:
            return await self._lanzar("cargue", {"confirmacion": pendientes})

        self._por_confirmar = cargar
        plural = "orden pendiente" if pendientes == 1 else "órdenes pendientes"
        return (
            f"Hay {pendientes} {plural} por crear en Biofile. ¿Hago el cargue real? Dime «sí» "
            "para confirmar."
        )

    def _hoy(self) -> date:
        return self._now().date()


# --- Texto ---


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos, sin "oye azul" ni "por favor"."""
    plano = unicodedata.normalize("NFD", texto.lower())
    plano = "".join(c for c in plano if unicodedata.category(c) != "Mn")
    plano = re.sub(r"[^\w/ ]+", " ", plano)
    plano = " ".join(plano.split())
    plano = re.sub(r"^(?:(?:oye|hey|ey) )?(?:azul )?(?:por favor |porfa )?", "", plano)
    plano = re.sub(r"(?: por favor| porfa| azul)+$", "", plano)
    return plano.strip()


def fechas(texto: str, hoy: date) -> tuple[date, date] | None:
    """Rango de fechas de lo que queda tras la orden; None si hay algo más que fechas."""
    resto = re.sub(r"^(?:con fecha )?(?:de |del |para |para el |de la fecha )?", "", texto.strip())
    if not resto:
        return hoy, hoy
    simples = {"hoy": hoy, "ayer": hoy - timedelta(days=1)}
    simples["anteayer"] = simples["antier"] = hoy - timedelta(days=2)
    if resto in simples:
        return simples[resto], simples[resto]
    if resto in ("esta semana", "la semana"):
        return hoy - timedelta(days=hoy.weekday()), hoy
    dia = rf"(\d{{1,2}})(?: de {_MES})?"
    encontrado = re.fullmatch(rf"(?:el )?{dia}(?: (?:hasta|al|a) (?:el )?(?:{dia}|hoy))?", resto)
    if encontrado is None:
        encontrado = re.fullmatch(
            rf"desde (?:el )?{dia}(?: (?:hasta|al|a) (?:el )?(?:{dia}|hoy))?", resto
        )
    if encontrado is None:
        return None
    d1, m1, d2, m2 = encontrado.groups()
    try:
        desde = _dia(int(d1), m1, hoy)
        hasta = _dia(int(d2), m2 or m1, hoy) if d2 else (hoy if "hoy" in resto else desde)
    except ValueError:
        return None
    return (desde, hasta) if desde <= hasta else None


def _dia(numero: int, mes: str | None, hoy: date) -> date:
    candidato = date(hoy.year, MESES.index(mes) + 1 if mes else hoy.month, numero)
    if candidato > hoy and mes is None:
        # "El 28" dicho el 3 de noviembre es el 28 de octubre.
        anterior = hoy.replace(day=1) - timedelta(days=1)
        candidato = date(anterior.year, anterior.month, numero)
    return candidato


def _fecha_hablada(dia: date, hoy: date) -> str:
    if dia == hoy:
        return "hoy"
    if dia == hoy - timedelta(days=1):
        return "ayer"
    return f"el {dia.day} de {MESES[dia.month - 1]}"


def _rango_hablado(datos: dict[str, Any], hoy: date) -> str:
    if "desde" not in datos:
        return ""
    desde = date.fromisoformat(str(datos["desde"]))
    hasta = date.fromisoformat(str(datos.get("hasta") or datos["desde"]))
    if desde == hasta:
        cuando = _fecha_hablada(desde, hoy)
        return f" de {cuando}" if cuando in ("hoy", "ayer") else f" del {cuando[3:]}"
    return f" desde {_fecha_hablada(desde, hoy)} hasta {_fecha_hablada(hasta, hoy)}"


def _resumen_hablado(datos: Any) -> str:
    if not isinstance(datos, dict):
        return "El tablero no devolvió el resumen."
    if datos.get("aviso") and not datos.get("excel"):
        return str(datos["aviso"])
    pendientes = int(datos.get("pendientes") or 0)
    creadas = int(datos.get("ya_creadas") or 0)
    partes = [
        f"Hay {pendientes} {'orden pendiente' if pendientes == 1 else 'órdenes pendientes'} "
        f"por cargar y {creadas} ya {'creada' if creadas == 1 else 'creadas'} del Excel actual."
    ]
    if datos.get("ultima_orden"):
        cuando = f", {datos['ultima_cuando']}" if datos.get("ultima_cuando") else ""
        partes.append(f"La última orden creada fue la {datos['ultima_orden']}{cuando}.")
    if datos.get("aviso"):
        partes.append(str(datos["aviso"]))
    return " ".join(partes)


def _progreso_hablado(datos: Any) -> str:
    if not isinstance(datos, dict) or not datos.get("etiqueta"):
        return "No hay ningún proceso corriendo ni ninguno reciente."
    lineas = [str(linea).strip() for linea in datos.get("lineas") or [] if str(linea).strip()]
    ultima = lineas[-1][:200] if lineas else ""
    minutos = int(datos.get("segundos") or 0) // 60
    lleva = f", lleva {minutos} minutos" if minutos else ""
    if datos.get("corriendo"):
        estado = f"{datos['etiqueta']} sigue corriendo{lleva}."
    elif datos.get("detenido"):
        estado = f"{datos['etiqueta']} se detuvo."
    elif datos.get("codigo") in (0, None):
        estado = f"{datos['etiqueta']} terminó."
    else:
        estado = f"{datos['etiqueta']} terminó con un error."
    return f"{estado} Lo último que dijo: {ultima}" if ultima else estado


def _itinerario_hablado(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No tienes nada pendiente en el correo."
    primeros = items[:3]
    detalle = "; ".join(
        f"{i.get('prioridad', '')}: {i.get('de', '')}, {i.get('asunto', '')}"
        + (f" ({i['accion']})" if i.get("accion") else "")
        for i in primeros
    )
    total = len(items)
    resto = f" Y {total - 3} más." if total > 3 else ""
    return f"Tienes {total} pendientes en el correo. Lo primero: {detalle}.{resto}"


def _ok(resultado: Any) -> bool:
    return isinstance(resultado, dict) and resultado.get("ok") is not False


def _motivo(resultado: Any) -> str:
    if isinstance(resultado, dict):
        return str(resultado.get("motivo") or resultado.get("error") or "el tablero no lo aceptó")
    return "el tablero no lo aceptó"


# --- Atajos ---


def _repetible(herramienta: str, entrada: dict[str, Any]) -> bool:
    if herramienta == "correo_itinerario":
        return True
    if herramienta == "red_nacional_ejecutar":
        return entrada.get("operacion") in _PROCESOS_REPETIBLES
    if herramienta == "red_nacional_consultar":
        return entrada.get("seccion") in _SECCIONES_CON_RESPUESTA and len(entrada) == 1
    return False


def _con_fechas_relativas(entrada: dict[str, Any], hoy: date) -> dict[str, Any] | None:
    """Las fechas de hoy y ayer quedan como {hoy}/{ayer}; otras fechas, no se aprenden."""
    plantilla = {}
    for clave, valor in entrada.items():
        if isinstance(valor, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
            if valor == hoy.isoformat():
                valor = "{hoy}"
            elif valor == (hoy - timedelta(days=1)).isoformat():
                valor = "{ayer}"
            else:
                return None
        plantilla[clave] = valor
    return plantilla


def _con_fechas_de_hoy(plantilla: dict[str, Any], hoy: date) -> dict[str, Any]:
    reemplazos = {"{hoy}": hoy.isoformat(), "{ayer}": (hoy - timedelta(days=1)).isoformat()}
    return {k: reemplazos.get(v, v) if isinstance(v, str) else v for k, v in plantilla.items()}

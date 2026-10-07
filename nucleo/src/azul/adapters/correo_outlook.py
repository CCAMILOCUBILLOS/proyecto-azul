"""El Outlook clásico del usuario (ADR 0037, 0040).

Busca y lee correos, deja correos nuevos o respuestas en Borradores y pone las
categorías de color. Los guiones están en outlook_powershell; se ejecutan en este
equipo o, con el ayudante, en el PC de Optometría (correo_remoto). Nunca envía.
"""

import asyncio
import html
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from azul.adapters import outlook_powershell
from azul.adapters.documentos_windows import parece_secreto
from azul.core.ports import CorreoError

log = logging.getLogger(__name__)

SEGUNDOS_OUTLOOK = 120  # si Outlook estaba cerrado, abrirlo "en frío" tarda
MAX_PALABRAS = 6
MAX_RESULTADOS = 10
MAX_DIAS = 90
MAX_CARACTERES = 15_000
MAX_ADJUNTOS_MB = 20

_FECHA_RECIBIDO = "urn:schemas:httpmail:datereceived"
_FECHA_ENVIADO = "http://schemas.microsoft.com/mapi/proptag/0x00390040"
# El índice cubre el texto completo del correo (textdescription), no solo el comienzo.
_CAMPOS_INDICE = (
    "urn:schemas:httpmail:subject",
    "urn:schemas:httpmail:fromname",
    "urn:schemas:httpmail:fromemail",
    "urn:schemas:httpmail:displayto",
    "urn:schemas:httpmail:textdescription",
)
_CAMPOS_RESPALDO = (
    "urn:schemas:httpmail:subject",
    "urn:schemas:httpmail:fromname",
    "urn:schemas:httpmail:displayto",
)

# Prioridad -> (categoría en Outlook, color). Colores de Outlook: 1 rojo, 2 naranja,
# 8 azul, 13 gris.
CATEGORIAS = {
    "urgente": ("Azul: Urgente", 1),
    "alta": ("Azul: Alta", 2),
    "normal": ("Azul: Normal", 8),
    "baja": ("Azul: Baja", 13),
}

Ejecutar = Callable[[str, dict[str, Any]], dict[str, Any]]


class CorreoOutlook:
    def __init__(self, ejecutar: Ejecutar | None = None, firma: str = "") -> None:
        self._ejecutar = ejecutar or _local
        # Nombre de la firma de Outlook para los correos de Azul ("" = la predeterminada).
        self._firma = firma

    async def buscar(self, texto: str, carpeta: str, dias: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._buscar, texto, carpeta, dias)

    async def leer(self, id_correo: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._leer, id_correo)

    async def crear_borrador(
        self, para: list[str], cc: list[str], asunto: str, cuerpo: str, adjuntos: list[str]
    ) -> dict[str, Any]:
        entrada = {
            "para": "; ".join(para),
            "cc": "; ".join(cc),
            "asunto": asunto,
            "html": _html(cuerpo),
            "adjuntos": _adjuntos(adjuntos),
            "firma": self._firma,
        }
        return await asyncio.to_thread(self._ejecutar, "borrador", entrada)

    async def responder_en_borrador(
        self, id_correo: str, cuerpo: str, a_todos: bool, adjuntos: list[str]
    ) -> dict[str, Any]:
        entrada = {
            "id": id_correo,
            "a_todos": a_todos,
            "html": _html(cuerpo),
            "adjuntos": _adjuntos(adjuntos),
            "firma": self._firma,
        }
        return await asyncio.to_thread(self._ejecutar, "responder", entrada)

    async def nuevos(self, desde: datetime, maximo: int) -> list[dict[str, Any]]:
        filtro = _filtro(_FECHA_RECIBIDO, desde.astimezone(UTC), [], (), "ci_phrasematch")
        entrada = {"carpeta": "recibidos", "filtro": filtro, "respaldo": filtro, "maximo": maximo}
        correos = (await asyncio.to_thread(self._ejecutar, "buscar", entrada)).get("correos") or []
        return [
            {**correo, "vista": " ".join(str(correo.get("vista") or "").split())}
            for correo in correos
        ]

    async def categorizar(self, prioridades: dict[str, str]) -> None:
        items = [
            {"id": id_correo, "categoria": CATEGORIAS[prioridad][0]}
            for id_correo, prioridad in prioridades.items()
            if prioridad in CATEGORIAS
        ]
        if not items:
            return
        entrada = {
            "categorias": [{"nombre": n, "color": c} for n, c in CATEGORIAS.values()],
            "items": items,
        }
        resultado = await asyncio.to_thread(self._ejecutar, "categorizar", entrada)
        if resultado.get("fallos"):
            log.warning("Outlook no dejó categorizar %s correos", resultado["fallos"])

    def _buscar(self, texto: str, carpeta: str, dias: int) -> list[dict[str, Any]]:
        enviados = carpeta == "enviados"
        desde = datetime.now(UTC) - timedelta(days=max(1, min(MAX_DIAS, dias)))
        palabras = re.findall(r"[\w@.\-]+", texto)[:MAX_PALABRAS]
        fecha = _FECHA_ENVIADO if enviados else _FECHA_RECIBIDO
        entrada = {
            "carpeta": "enviados" if enviados else "recibidos",
            "filtro": _filtro(fecha, desde, palabras, _CAMPOS_INDICE, "ci_phrasematch"),
            "respaldo": _filtro(fecha, desde, palabras, _CAMPOS_RESPALDO, "like"),
            "maximo": MAX_RESULTADOS,
        }
        correos = self._ejecutar("buscar", entrada).get("correos") or []
        return [
            {**correo, "vista": " ".join(str(correo.get("vista") or "").split())[:200]}
            for correo in correos
        ]

    def _leer(self, id_correo: str) -> dict[str, Any]:
        correo = self._ejecutar("leer", {"id": id_correo})
        cuerpo = str(correo.get("cuerpo") or "")
        if len(cuerpo) > MAX_CARACTERES:
            correo["cuerpo"] = cuerpo[:MAX_CARACTERES] + "\n…(el correo sigue; esto es lo primero)"
        return correo


def _filtro(
    fecha: str, desde: datetime, palabras: list[str], campos: tuple[str, ...], operador: str
) -> str:
    """Filtro DASL de Outlook: desde la fecha (UTC) y cada palabra en alguno de los campos."""
    partes = [f"\"{fecha}\" >= '{desde:%Y-%m-%d %H:%M}'"]
    for palabra in palabras:
        valor = f"'%{palabra}%'" if operador == "like" else f"'{palabra}'"
        partes.append("(" + " OR ".join(f'"{c}" {operador} {valor}' for c in campos) + ")")
    return "@SQL=" + " AND ".join(partes)


def _html(texto: str) -> str:
    """Texto plano a párrafos con el estilo normal de Outlook (sin cambiar su fuente)."""
    bloques = [b.strip() for b in re.split(r"\n\s*\n", texto.strip()) if b.strip()]
    parrafos = [
        "<p class=MsoNormal>"
        + "<br>".join(html.escape(linea.strip()) for linea in bloque.splitlines())
        + "</p>"
        for bloque in bloques
    ]
    # Outlook separa los párrafos con uno vacío; el último aparta la firma o la cita.
    vacio = "<p class=MsoNormal>&nbsp;</p>"
    return vacio.join(parrafos) + vacio


def _adjuntos(rutas: list[str]) -> list[str]:
    archivos = []
    total = 0
    for texto in rutas:
        ruta = Path(texto)
        if parece_secreto(ruta.name):
            raise CorreoError(f"{ruta.name} parece guardar claves; por seguridad no lo adjunto.")
        if not ruta.is_file():
            raise CorreoError(f"No encuentro el archivo para adjuntar: {ruta.name}")
        total += ruta.stat().st_size
        archivos.append(str(ruta.resolve()))
    if total > MAX_ADJUNTOS_MB * 1024 * 1024:
        raise CorreoError(f"Los adjuntos pasan de {MAX_ADJUNTOS_MB} MB; el correo no saldría.")
    return archivos


def _local(accion: str, entrada: dict[str, Any]) -> dict[str, Any]:
    try:
        return outlook_powershell.ejecutar(accion, entrada)
    except outlook_powershell.OutlookError as error:
        raise CorreoError(str(error)) from error

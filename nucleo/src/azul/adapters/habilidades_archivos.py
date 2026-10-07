"""Las habilidades de Azul: una carpeta por habilidad con su SKILL.md (ADR 0032).

Mismo formato que las habilidades de Claude: un encabezado con `name` y
`description`, y debajo las instrucciones. Así se pueden reutilizar habilidades
existentes o escribir nuevas en español.
"""

import logging
import re
from pathlib import Path

from azul.core.ports import Habilidad

log = logging.getLogger(__name__)

_ENCABEZADO = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def cargar_habilidades(carpeta: Path) -> list[Habilidad]:
    if not carpeta.is_dir():
        return []
    habilidades = []
    for archivo in sorted(carpeta.glob("*/SKILL.md")):
        habilidad = _leer(archivo)
        if habilidad:
            habilidades.append(habilidad)
    return habilidades


def _leer(archivo: Path) -> Habilidad | None:
    texto = archivo.read_text(encoding="utf-8")
    partes = _ENCABEZADO.match(texto)
    if not partes:
        log.warning("Habilidad sin encabezado: %s", archivo.parent.name)
        return None
    campos = dict(
        (clave.strip().lower(), valor.strip().strip("\"'"))
        for clave, _, valor in (
            linea.partition(":") for linea in partes.group(1).splitlines() if ":" in linea
        )
    )
    nombre = campos.get("name") or archivo.parent.name
    descripcion = campos.get("description", "")
    if not descripcion:
        log.warning("Habilidad sin descripción: %s", nombre)
        return None
    return Habilidad(nombre=nombre, descripcion=descripcion, instrucciones=partes.group(2).strip())

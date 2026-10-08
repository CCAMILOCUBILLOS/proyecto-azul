"""Archivos y Python en el portátil o en el PC de Optometría (ADR 0041).

Las acciones son las de archivos_basicos: en el portátil se ejecutan aquí; en
Optometría, a través del ayudante (/archivos), que usa ese mismo archivo.
"""

import asyncio
from pathlib import Path
from typing import Any

from azul.adapters import archivos_basicos
from azul.adapters.correo_remoto import Ejecutar, ejecutor_remoto
from azul.core.ports import ArchivosError


class ArchivosEn:
    def __init__(self, ejecutar: Ejecutar) -> None:
        self._ejecutar = ejecutar

    async def hacer(self, accion: str, entrada: dict[str, Any]) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(self._ejecutar, accion, entrada)
        except archivos_basicos.ArchivoError as error:
            raise ArchivosError(str(error)) from error


def archivos_locales(respaldos: Path, trabajo: Path) -> ArchivosEn:
    config = {
        "respaldos": str(respaldos),
        "trabajo": str(trabajo),
        "raices": archivos_basicos.raices_por_defecto(),
    }
    return ArchivosEn(lambda accion, entrada: archivos_basicos.ejecutar(accion, entrada, config))


def archivos_remotos(url: str, clave: str) -> ArchivosEn:
    return ArchivosEn(ejecutor_remoto(url, clave, ruta="/archivos", error=ArchivosError))

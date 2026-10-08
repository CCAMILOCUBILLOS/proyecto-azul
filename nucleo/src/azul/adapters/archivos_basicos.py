"""Manejar archivos y correr Python en un equipo (ADR 0041).

Solo usa la biblioteca estándar de Python (3.8 o más nueva): lo usa Azul en el
portátil y el ayudante en el PC de Optometría.

Reglas que valen en ambos equipos:
- Todo el equipo, salvo las carpetas del sistema (Windows, Program Files, AppData…)
  y los archivos que parecen guardar claves (.env, "clave", "token"…).
- Antes de cambiar o reemplazar un archivo, una copia de seguridad (respaldar), y
  restaurar() deshace el último cambio.
- Copiar y mover nunca sobrescriben; borrar solo manda a la Papelera.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_CARACTERES = 60_000
MAX_LISTADO = 200
MAX_RESULTADOS = 20
SEGUNDOS_BUSCANDO = 10.0
SEGUNDOS_PYTHON = 120
MAX_SALIDA = 12_000

SISTEMA = {
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
    "$recycle.bin",
    "system volume information",
    "recovery",
    "perflogs",
}
_SALTAR_AL_BUSCAR = SISTEMA | {"node_modules", ".git", ".venv", "__pycache__"}
_SECRETO = re.compile(r"(^\.env)|key|clave|password|contrase|secret|token|\.pem$|\.pfx$", re.I)


class ArchivoError(Exception):
    """Fallo con un archivo, con un mensaje apto para el usuario."""


def parece_secreto(nombre: str) -> bool:
    return bool(_SECRETO.search(nombre))


def validar(ruta: str, *, debe_existir: bool = True) -> Path:
    texto = str(ruta or "").strip().strip('"')
    if not texto:
        raise ArchivoError("Falta la ruta.")
    p = Path(texto).expanduser()
    if not p.is_absolute():
        raise ArchivoError("Necesito la ruta completa (por ejemplo C:\\Users\\...\\archivo.py).")
    p = p.resolve()
    if any(parte.lower() in SISTEMA for parte in p.parts[1:]) and not _en_temporales(p):
        raise ArchivoError("Esa ruta está en una carpeta del sistema; no la toco.")
    if parece_secreto(p.name):
        raise ArchivoError("Ese archivo parece guardar claves; por seguridad no lo toco.")
    if debe_existir and not p.exists():
        raise ArchivoError(f"No encuentro {p}.")
    return p


# --- Leer y buscar ---


def listar(carpeta: str) -> dict[str, Any]:
    p = validar(carpeta)
    if not p.is_dir():
        raise ArchivoError("Eso no es una carpeta.")
    elementos = []
    for hijo in sorted(p.iterdir(), key=lambda h: (not h.is_dir(), h.name.lower())):
        if len(elementos) >= MAX_LISTADO:
            break
        try:
            info = hijo.stat()
        except OSError:
            continue
        elementos.append(
            {
                "nombre": hijo.name,
                "tipo": "carpeta" if hijo.is_dir() else "archivo",
                "tamano_kb": round(info.st_size / 1024, 1) if hijo.is_file() else None,
                "modificado": datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return {"carpeta": str(p), "elementos": elementos}


def buscar(texto: str, raices: list[str]) -> dict[str, Any]:
    palabras = texto.lower().split()
    if not palabras:
        raise ArchivoError("Falta qué buscar.")
    limite = time.monotonic() + SEGUNDOS_BUSCANDO
    encontrados: list[Path] = []
    for raiz in raices:
        if not Path(raiz).is_dir():
            continue
        for carpeta, subcarpetas, archivos in os.walk(raiz):
            subcarpetas[:] = [
                s
                for s in subcarpetas
                if s.lower() not in _SALTAR_AL_BUSCAR and not s.startswith(".")
            ]
            for nombre in [*subcarpetas, *archivos]:
                if all(p in nombre.lower() for p in palabras):
                    encontrados.append(Path(carpeta, nombre))
            if len(encontrados) >= MAX_RESULTADOS * 3 or time.monotonic() > limite:
                break
    vistos: dict[str, Path] = {str(r).lower(): r for r in encontrados}
    unicos = sorted(vistos.values(), key=_fecha, reverse=True)[:MAX_RESULTADOS]
    return {"encontrados": [str(r) for r in unicos]}


def leer(ruta: str) -> dict[str, Any]:
    p = validar(ruta)
    if not p.is_file():
        raise ArchivoError("Eso no es un archivo.")
    texto, _ = _leer_texto(p)
    if len(texto) > MAX_CARACTERES:
        texto = texto[:MAX_CARACTERES] + "\n…(el archivo sigue; esto es lo primero)"
    return {"ruta": str(p), "texto": texto}


# --- Cambiar (siempre con copia de seguridad) ---


def editar(
    ruta: str, buscar_texto: str, reemplazo: str, todas: bool, respaldos: str
) -> dict[str, Any]:
    p = validar(ruta)
    if not p.is_file():
        raise ArchivoError("Eso no es un archivo.")
    if not buscar_texto:
        raise ArchivoError("Falta el texto a buscar.")
    texto, codificacion = _leer_texto(p)
    if "\r\n" in texto and "\r" not in buscar_texto:
        # El archivo usa saltos de Windows; lo pedido llega con saltos simples.
        buscar_texto = buscar_texto.replace("\n", "\r\n")
        reemplazo = reemplazo.replace("\n", "\r\n")
    veces = texto.count(buscar_texto)
    if veces == 0:
        raise ArchivoError(
            "No encontré ese texto exacto en el archivo. Léelo de nuevo y copia el texto tal "
            "cual (espacios y sangría incluidos)."
        )
    if veces > 1 and not todas:
        raise ArchivoError(
            f"Ese texto aparece {veces} veces. Incluye más contexto para que sea único, o pide "
            "cambiar todas."
        )
    copia = respaldar(p, respaldos)
    p.write_bytes(texto.replace(buscar_texto, reemplazo).encode(codificacion))
    return {"ruta": str(p), "cambios": veces, "respaldo": copia}


def escribir(ruta: str, contenido: str, respaldos: str) -> dict[str, Any]:
    p = validar(ruta, debe_existir=False)
    copia = None
    if p.exists():
        if not p.is_file():
            raise ArchivoError("Ahí hay una carpeta, no un archivo.")
        copia = respaldar(p, respaldos)
        anterior, _ = _leer_texto(p)
        if "\r\n" in anterior and "\r\n" not in contenido:
            contenido = contenido.replace("\n", "\r\n")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenido, encoding="utf-8", newline="")
    return {"ruta": str(p), "nuevo": copia is None, "respaldo": copia}


def respaldar(p: Path, respaldos: str) -> str:
    """Copia el archivo a la carpeta de respaldos y lo anota en su índice."""
    carpeta = Path(respaldos) / datetime.now().strftime("%Y-%m-%d")
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = _libre(carpeta / f"{datetime.now():%H%M%S}_{p.name}")
    shutil.copy2(p, destino)
    with open(Path(respaldos) / "indice.txt", "a", encoding="utf-8") as indice:
        indice.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{p}\t{destino}\n")
    return str(destino)


def restaurar(ruta: str, respaldos: str) -> dict[str, Any]:
    """Deshace el último cambio: vuelve a poner la copia más reciente de ese archivo."""
    p = validar(ruta, debe_existir=False)
    indice = Path(respaldos) / "indice.txt"
    copias = []
    if indice.exists():
        for linea in indice.read_text(encoding="utf-8").splitlines():
            partes = linea.split("\t")
            if len(partes) == 3 and Path(partes[1]) == p and Path(partes[2]).is_file():
                copias.append(partes[2])
    if not copias:
        raise ArchivoError("No tengo copias de seguridad de ese archivo.")
    ultima = copias[-1]
    actual = respaldar(p, respaldos) if p.exists() else None
    shutil.copy2(ultima, p)
    # La copia que se acaba de restaurar ya no cuenta: así otro "deshacer" va más atrás.
    lineas = indice.read_text(encoding="utf-8").splitlines()
    lineas = [ln for ln in lineas if not ln.endswith("\t" + ultima)]
    indice.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return {"ruta": str(p), "restaurado_desde": ultima, "respaldo_de_lo_que_habia": actual}


# --- Organizar ---


def copiar(origen: str, destino: str) -> dict[str, Any]:
    o = validar(origen)
    d = _destino(o, destino)
    if o.is_dir():
        shutil.copytree(o, d)
    else:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(o, d)
    return {"origen": str(o), "destino": str(d)}


def mover(origen: str, destino: str) -> dict[str, Any]:
    o = validar(origen)
    d = _destino(o, destino)
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(o), str(d))
    return {"origen": str(o), "destino": str(d)}


def crear_carpeta(ruta: str) -> dict[str, Any]:
    p = validar(ruta, debe_existir=False)
    p.mkdir(parents=True, exist_ok=True)
    return {"carpeta": str(p)}


def a_papelera(ruta: str) -> dict[str, Any]:
    p = validar(ruta)
    metodo = "DeleteDirectory" if p.is_dir() else "DeleteFile"
    guion = (
        "Add-Type -AssemblyName Microsoft.VisualBasic;"
        f"[Microsoft.VisualBasic.FileIO.FileSystem]::{metodo}($env:AZUL_RUTA,"
        "'OnlyErrorDialogs','SendToRecycleBin')"
    )
    codificado = base64.b64encode(guion.encode("utf-16-le")).decode("ascii")
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
            env={**os.environ, "AZUL_RUTA": str(p)},
            capture_output=True,
            timeout=60,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise ArchivoError("No pude mandarlo a la Papelera.") from error
    return {"a_la_papelera": str(p)}


# --- Correr Python ---


def correr_python(codigo: str, trabajo: str, carpeta: str = "") -> dict[str, Any]:
    """Guarda el programa en la carpeta de trabajo y lo corre con tiempo límite."""
    if not codigo.strip():
        raise ArchivoError("Falta el código.")
    lugar = validar(carpeta) if carpeta else Path(trabajo)
    Path(trabajo).mkdir(parents=True, exist_ok=True)
    programa = _libre(Path(trabajo) / f"azul_{datetime.now():%Y%m%d_%H%M%S}.py")
    programa.write_text(codigo, encoding="utf-8")
    try:
        hecho = subprocess.run(
            [sys.executable, str(programa)],
            cwd=str(lugar),
            capture_output=True,
            timeout=SEGUNDOS_PYTHON,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise ArchivoError(
            f"El programa pasó de {SEGUNDOS_PYTHON} segundos y lo detuve. Quedó en {programa}."
        ) from None
    return {
        "programa": str(programa),
        "codigo_de_salida": hecho.returncode,
        "salida": _recortar(hecho.stdout.decode("utf-8", "replace")),
        "errores": _recortar(hecho.stderr.decode("utf-8", "replace")),
    }


# --- Para el ayudante: una acción por nombre ---


def ejecutar(accion: str, entrada: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """config: respaldos, trabajo y raices (carpetas donde buscar) de ese equipo."""
    e = entrada
    acciones = {
        "listar": lambda: listar(e.get("carpeta", "")),
        "buscar": lambda: buscar(e.get("texto", ""), config["raices"]),
        "leer": lambda: leer(e.get("ruta", "")),
        "editar": lambda: editar(
            e.get("ruta", ""),
            e.get("buscar", ""),
            e.get("reemplazo", ""),
            bool(e.get("todas")),
            config["respaldos"],
        ),
        "escribir": lambda: escribir(
            e.get("ruta", ""), e.get("contenido", ""), config["respaldos"]
        ),
        "restaurar": lambda: restaurar(e.get("ruta", ""), config["respaldos"]),
        "copiar": lambda: copiar(e.get("ruta", ""), e.get("destino", "")),
        "mover": lambda: mover(e.get("ruta", ""), e.get("destino", "")),
        "crear_carpeta": lambda: crear_carpeta(e.get("ruta", "")),
        "papelera": lambda: a_papelera(e.get("ruta", "")),
        "python": lambda: correr_python(
            e.get("codigo", ""), config["trabajo"], e.get("carpeta", "")
        ),
    }
    if accion not in acciones:
        raise ArchivoError("Acción desconocida.")
    try:
        return acciones[accion]()
    except ArchivoError:
        raise
    except FileExistsError as error:
        raise ArchivoError(f"Ya existe {error.filename}; no lo sobrescribo.") from error
    except PermissionError as error:
        raise ArchivoError("Windows no me deja: el archivo está abierto o protegido.") from error
    except OSError as error:
        raise ArchivoError(f"No pude hacerlo: {error.strerror or 'error del sistema'}.") from error


ACCIONES = (
    "listar",
    "buscar",
    "leer",
    "editar",
    "escribir",
    "restaurar",
    "copiar",
    "mover",
    "crear_carpeta",
    "papelera",
    "python",
)


def raices_por_defecto() -> list[str]:
    casa = Path.home()
    probables = [casa / "Desktop", casa / "Documents", casa / "OneDrive", casa]
    unidades = [Path(f"{letra}:\\") for letra in "CDE" if Path(f"{letra}:\\").is_dir()]
    return [str(r) for r in [*probables, *unidades] if r.is_dir()]


def _en_temporales(p: Path) -> bool:
    """La carpeta Temp vive dentro de AppData, pero es inofensiva (el resto de AppData no)."""
    temporales = Path(tempfile.gettempdir()).resolve()
    return p == temporales or temporales in p.parents


def _destino(origen: Path, destino: str) -> Path:
    d = validar(destino, debe_existir=False)
    if d.is_dir():
        d = d / origen.name
    if d.exists():
        raise ArchivoError(f"Ya existe {d}; no lo sobrescribo. Elige otro nombre.")
    return d


def _leer_texto(p: Path) -> tuple[str, str]:
    crudo = p.read_bytes()
    if b"\x00" in crudo[:4000]:
        raise ArchivoError(
            "Ese archivo no es de texto (es binario); no lo puedo leer ni editar así."
        )
    for codificacion in ("utf-8-sig" if crudo.startswith(b"\xef\xbb\xbf") else "utf-8", "cp1252"):
        try:
            return crudo.decode(codificacion), codificacion
        except UnicodeDecodeError:
            continue
    return crudo.decode("latin-1"), "latin-1"


def _libre(p: Path) -> Path:
    if not p.exists():
        return p
    n = 2
    while True:
        candidato = p.with_name(f"{p.stem} ({n}){p.suffix}")
        if not candidato.exists():
            return candidato
        n += 1


def _fecha(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _recortar(texto: str) -> str:
    return texto if len(texto) <= MAX_SALIDA else texto[:MAX_SALIDA] + "\n…(recortado)"

"""Herramientas de habilidades y documentos para el cerebro (ADR 0032).

- usar_habilidad: abre las instrucciones de una habilidad (redacción, …) solo
  cuando hace falta; el cerebro ve de antemano solo la lista.
- buscar_archivos, leer_documento, pdf_a_word, crear_word: trabajan con los
  archivos del usuario en el portátil. Nada se borra ni se sobrescribe.
"""

import json
from collections.abc import Callable
from typing import Any

from azul.core.ports import Documentos, DocumentosError, Habilidad, ToolSpec

EXTENSIONES = (
    "docx",
    "pdf",
    "txt",
    "md",
    "xlsx",
    "csv",
    "doc",
    "pptx",
    "html",
    "css",
    "js",
    "ts",
    "py",
    "json",
    "sql",
)
ESCRIBIBLES = ("html", "css", "js", "ts", "py", "md", "txt", "json", "csv", "sql", "xml", "yaml")
_CELDA = {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}, {"type": "null"}]}


def herramienta_habilidades(habilidades: list[Habilidad]) -> ToolSpec | None:
    if not habilidades:
        return None
    por_nombre = {h.nombre: h for h in habilidades}

    async def usar(entrada: dict[str, Any]) -> str:
        habilidad = por_nombre.get(str(entrada.get("nombre", "")))
        if habilidad is None:
            raise ValueError("No tengo esa habilidad.")
        return habilidad.instrucciones

    return ToolSpec(
        name="usar_habilidad",
        description=(
            "Abre las instrucciones de una de tus habilidades. Úsala ANTES de hacer una tarea "
            "que corresponda a una habilidad de la lista (en tus instrucciones), y síguelas."
        ),
        input_schema={
            "type": "object",
            "properties": {"nombre": {"type": "string", "enum": list(por_nombre)}},
            "required": ["nombre"],
            "additionalProperties": False,
        },
        handler=usar,
    )


def herramientas_documentos(
    documentos: Documentos, anotar: Callable[[str], None]
) -> list[ToolSpec]:
    async def buscar(entrada: dict[str, Any]) -> str:
        texto = str(entrada.get("texto", "")).strip()
        if not texto:
            raise ValueError("Falta qué buscar.")
        tipos = [t for t in entrada.get("tipos") or [] if t in EXTENSIONES]
        encontrados = await _llamar(documentos.buscar(texto, tipos))
        anotar("archivos del PC")
        if not encontrados:
            return "No encontré archivos con ese nombre."
        return json.dumps(encontrados, ensure_ascii=False)

    async def leer(entrada: dict[str, Any]) -> str:
        contenido = await _llamar(documentos.leer(_ruta(entrada)))
        anotar("archivos del PC")
        return contenido

    async def convertir(entrada: dict[str, Any]) -> str:
        nueva = await _llamar(documentos.pdf_a_word(_ruta(entrada)))
        anotar("archivos del PC")
        return f"Convertido. El Word quedó en: {nueva}"

    async def crear_excel(entrada: dict[str, Any]) -> str:
        titulo = str(entrada.get("titulo", "")).strip()
        hojas = entrada.get("hojas")
        if not titulo or not isinstance(hojas, list) or not hojas:
            raise ValueError("Faltan el título o las hojas.")
        ruta = await _llamar(documentos.crear_excel(titulo, hojas))
        anotar("archivos del PC")
        return f"Guardado en: {ruta}"

    async def guardar(entrada: dict[str, Any]) -> str:
        nombre = str(entrada.get("nombre", "")).strip()
        extension = str(entrada.get("extension", "")).strip()
        contenido = str(entrada.get("contenido", ""))
        if not nombre or not extension or not contenido.strip():
            raise ValueError("Faltan el nombre, la extensión o el contenido.")
        ruta = await _llamar(documentos.guardar_archivo(nombre, extension, contenido))
        anotar("archivos del PC")
        return f"Guardado en: {ruta}"

    async def crear(entrada: dict[str, Any]) -> str:
        titulo = str(entrada.get("titulo", "")).strip()
        contenido = str(entrada.get("contenido", "")).strip()
        if not titulo or not contenido:
            raise ValueError("Faltan el título o el contenido.")
        modelo = str(entrada.get("modelo") or "").strip() or None
        ruta = await _llamar(documentos.crear_word(titulo, contenido, modelo))
        anotar("archivos del PC")
        return f"Guardado en: {ruta}"

    ruta_schema = {
        "type": "string",
        "description": "Ruta completa, tal como la dio buscar_archivos.",
    }
    return [
        ToolSpec(
            name="buscar_archivos",
            description=(
                "Busca archivos en el PC del usuario por palabras de su nombre (no por su "
                "contenido). Devuelve rutas, tamaño y fecha; si hay varios, pregunta cuál."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Palabras del nombre del archivo."},
                    "tipos": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(EXTENSIONES)},
                        "description": "Solo estos tipos (vacío: todos los documentos).",
                    },
                },
                "required": ["texto"],
                "additionalProperties": False,
            },
            handler=buscar,
        ),
        ToolSpec(
            name="leer_documento",
            description=(
                "Lee un archivo del PC del usuario: Word, PDF, Excel (cada hoja con sus filas), "
                "CSV, texto o código fuente."
            ),
            input_schema={
                "type": "object",
                "properties": {"ruta": ruta_schema},
                "required": ["ruta"],
                "additionalProperties": False,
            },
            handler=leer,
        ),
        ToolSpec(
            name="pdf_a_word",
            description=(
                "Convierte un PDF a Word con el Microsoft Word del usuario, conservando el "
                "formato lo mejor posible. El original no se toca."
            ),
            input_schema={
                "type": "object",
                "properties": {"ruta": ruta_schema},
                "required": ["ruta"],
                "additionalProperties": False,
            },
            handler=convertir,
        ),
        ToolSpec(
            name="crear_word",
            description=(
                "Crea un documento Word nuevo en OneDrive/Azul/Documentos. Si das un 'modelo' "
                "(un .docx), conserva su membrete, encabezado y estilos y reemplaza el cuerpo. "
                "En 'contenido': un párrafo por línea en blanco; '# ' y '## ' para títulos; "
                "'- ' para viñetas. Nunca sobrescribe: si el nombre existe, crea otra versión."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Nombre del archivo, sin .docx."},
                    "contenido": {"type": "string"},
                    "modelo": ruta_schema,
                },
                "required": ["titulo", "contenido"],
                "additionalProperties": False,
            },
            handler=crear,
        ),
        ToolSpec(
            name="crear_excel",
            description=(
                "Crea un Excel nuevo en OneDrive/Azul/Documentos. Cada hoja es una lista de "
                "filas; la primera fila es el encabezado (queda en negrita y fija). Usa números "
                "como números (no como texto) y fórmulas de Excel en inglés empezando por '=' "
                "(=SUM(B2:B10), =AVERAGE(...)). Nunca sobrescribe."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Nombre del archivo, sin .xlsx."},
                    "hojas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nombre": {"type": "string"},
                                "filas": {
                                    "type": "array",
                                    "items": {"type": "array", "items": _CELDA},
                                },
                            },
                            "required": ["nombre", "filas"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["titulo", "hojas"],
                "additionalProperties": False,
            },
            handler=crear_excel,
        ),
        ToolSpec(
            name="guardar_archivo",
            description=(
                "Guarda un archivo de texto o código en OneDrive/Azul/Documentos: páginas e "
                "interfaces (html, css, js), programas (py, ts, sql…), notas (md, txt) o datos "
                "(json, csv). Una página HTML debe ser completa y abrir sola en el navegador. "
                "Nunca sobrescribe."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del archivo, sin extensión.",
                    },
                    "extension": {"type": "string", "enum": list(ESCRIBIBLES)},
                    "contenido": {"type": "string"},
                },
                "required": ["nombre", "extension", "contenido"],
                "additionalProperties": False,
            },
            handler=guardar,
        ),
    ]


def _ruta(entrada: dict[str, Any]) -> str:
    ruta = str(entrada.get("ruta", "")).strip()
    if not ruta:
        raise ValueError("Falta la ruta del archivo.")
    return ruta


async def _llamar(llamada: Any) -> Any:
    try:
        return await llamada
    except DocumentosError as error:
        raise ValueError(str(error)) from error

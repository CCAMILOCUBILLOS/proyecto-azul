"""Herramientas para que Azul maneje el tablero de Red Nacional (ADR 0031).

El tablero (Tablero.bat, en el PC de Optometría) ya hace todo el trabajo:
leer correos, preparar agendamientos, crear órdenes en Biofile, llevar el
seguimiento. Azul solo le pide lo mismo que piden sus botones, por voz.

Por decisión del usuario, Azul actúa con autonomía total (ADR 0012), también
en el cargue real; por eso las descripciones le piden decir siempre, en voz
alta, qué lanzó.
"""

import json
from collections.abc import Callable
from typing import Any

from azul.core.ports import RedNacional, RedNacionalError, ToolSpec

# Lo que se le entrega al cerebro de una consulta: suficiente para responder sin
# llenar la conversación (y la cuenta) con tablas enteras.
MAX_RESULT_CHARS = 12_000

SECCIONES: dict[str, str] = {
    "resumen": "las cifras de arriba del tablero: Excel actual, órdenes pendientes por "
    "cargar, ya creadas, total histórico y la última orden creada",
    "seguimiento": "cada agendamiento (usuario, IPS, cliente) con sus etapas y alertas",
    "progreso": "lo que está corriendo ahora o lo último que corrió, con su registro",
    "ventas": "estado de los archivos del informe de ventas",
    "ventas_red": "las ventas de red nacional (VENTAS OCUPACIONAL)",
    "control": "la conexión con el Excel CONTROL RED NACIONAL de SharePoint",
    "directorio": "las IPS aliadas por ciudad, si son de la alianza y sus tarifas",
    "clientes": "el listado de clientes (empresas)",
    "cliente_perfil": "el profesiograma de un cliente (pide 'clave')",
    "cliente_bateria": "la batería fija de exámenes de una empresa (pide 'nombre')",
    "cliente_cargo": "los exámenes de un cargo de un cliente (pide 'clave' y 'cargo')",
    "cliente_acuerdo": "el acuerdo comercial (precios) de un cliente (pide 'clave')",
}

PROCESOS: dict[str, str] = {
    "simulacion": "simula el cargue: revisa el Excel sin tocar Biofile",
    "verificar": "revisa el catálogo de exámenes contra Biofile",
    "cargue": "CARGUE REAL: crea las órdenes pendientes en Biofile (opcional 'maximo')",
    "correos": "lee los correos de Outlook y arma el Excel de red nacional (pide fechas)",
    "agendar_simulacion": "simula el agendamiento con las IPS (pide fechas)",
    "agendar": "deja en Outlook los borradores para las IPS; no envía nada (pide fechas)",
    "base": "baja de Biofile la base de órdenes que evita duplicados (fechas opcionales)",
    "ventas": "informe de ventas (pide fechas y qué pasos: biofile, drive, informe)",
    "ventas_acuerdos": "revisa si hay acuerdos comerciales nuevos",
    "control_probar": "prueba la conexión con CONTROL RED NACIONAL (no escribe)",
    "control_sync": "lleva las órdenes creadas al Excel CONTROL RED NACIONAL",
    "control_conectar": "conecta la cuenta de Microsoft para CONTROL RED NACIONAL",
    "sincronizar_seguimiento": "actualiza el seguimiento con lo agendado (fechas opcionales)",
    "marcar_seguimiento": "cambia a mano el estado de un agendamiento (pide 'id' y 'estado')",
    "reporte": "genera el reporte en Excel de red nacional",
    "detener": "detiene el proceso que esté corriendo",
}

ESTADOS_SEGUIMIENTO = ("BORRADOR", "AGENDADO", "ENVIADO", "NO_PRESENTO", "SI_PRESENTO")

_FECHA = {"type": "string", "description": "Fecha AAAA-MM-DD."}


def herramientas_red_nacional(
    tablero: RedNacional, anotar: Callable[[str], None]
) -> list[ToolSpec]:
    """Las dos herramientas: consultar y ejecutar. `anotar` registra lo consultado (ADR 0027)."""

    async def consultar(entrada: dict[str, Any]) -> str:
        seccion = str(entrada.get("seccion", ""))
        if seccion not in SECCIONES:
            raise ValueError(f"No conozco la sección «{seccion}».")
        parametros = {
            clave: str(entrada[clave])
            for clave in ("clave", "nombre", "cargo")
            if entrada.get(clave)
        }
        resultado = await _llamar(tablero.consultar(seccion, parametros))
        anotar(f"red nacional: {seccion}")
        return _para_el_cerebro(resultado)

    async def ejecutar(entrada: dict[str, Any]) -> str:
        operacion = str(entrada.get("operacion", ""))
        if operacion not in PROCESOS:
            raise ValueError(f"No conozco el proceso «{operacion}».")
        datos = {
            clave: valor
            for clave, valor in entrada.items()
            if clave != "operacion" and valor not in (None, "")
        }
        if operacion == "cargue" and "confirmacion" not in datos:
            datos["confirmacion"] = await _a_crear(tablero, datos.get("maximo"))
        resultado = await _llamar(tablero.ejecutar(operacion, datos))
        anotar(f"red nacional: {operacion}")
        return _para_el_cerebro(resultado)

    return [
        ToolSpec(
            name="red_nacional_consultar",
            description=(
                "Consulta el tablero de Red Nacional de Confianza IPS (atenciones de salud "
                "ocupacional fuera de Villavicencio, con IPS aliadas). Secciones: "
                + "; ".join(f"{nombre}: {texto}" for nombre, texto in SECCIONES.items())
                + ". Úsala para cualquier pregunta sobre órdenes, agendamientos, IPS, "
                "clientes o ventas de red nacional, en vez de suponer."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "seccion": {"type": "string", "enum": list(SECCIONES)},
                    "clave": {"type": "string", "description": "Clave del cliente."},
                    "nombre": {"type": "string", "description": "Nombre de la empresa."},
                    "cargo": {"type": "string", "description": "Cargo a consultar."},
                },
                "required": ["seccion"],
                "additionalProperties": False,
            },
            handler=consultar,
        ),
        ToolSpec(
            name="red_nacional_ejecutar",
            description=(
                "Lanza un proceso en el tablero de Red Nacional (corre en el PC de "
                "Optometría). Procesos: "
                + "; ".join(f"{nombre}: {texto}" for nombre, texto in PROCESOS.items())
                + ". Lánzalo apenas el usuario lo pida, sin pedir confirmación, pero di "
                "siempre en voz alta exactamente qué lanzaste (y si es real o simulación). "
                "Si el usuario dice algo ambiguo entre simular y cargar de verdad, pregunta "
                "cuál. Los procesos corren en segundo plano: para saber cómo van, consulta "
                "la sección progreso. Las fechas relativas (hoy, esta semana) se calculan "
                "con la fecha actual."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "operacion": {"type": "string", "enum": list(PROCESOS)},
                    "desde": _FECHA,
                    "hasta": _FECHA,
                    "maximo": {
                        "type": "integer",
                        "description": "Cargue: crear como mucho estas órdenes.",
                    },
                    "id": {"type": "string", "description": "Id del agendamiento a marcar."},
                    "estado": {"type": "string", "enum": list(ESTADOS_SEGUIMIENTO)},
                    "biofile": {"type": "boolean", "description": "Ventas: bajar de Biofile."},
                    "drive": {"type": "boolean", "description": "Ventas: bajar de Drive."},
                    "informe": {"type": "boolean", "description": "Ventas: generar informe."},
                },
                "required": ["operacion"],
                "additionalProperties": False,
            },
            handler=ejecutar,
        ),
    ]


async def _a_crear(tablero: RedNacional, maximo: Any) -> int:
    """El tablero exige el número exacto de órdenes que se van a crear (su confirmación)."""
    resumen = await _llamar(tablero.consultar("resumen", {}))
    pendientes = int(resumen.get("pendientes", 0)) if isinstance(resumen, dict) else 0
    if isinstance(maximo, int) and maximo > 0:
        return min(maximo, pendientes)
    return pendientes


async def _llamar(llamada: Any) -> Any:
    try:
        return await llamada
    except RedNacionalError as error:
        raise ValueError(str(error)) from error


def _para_el_cerebro(resultado: Any) -> str:
    texto = json.dumps(resultado, ensure_ascii=False)
    if len(texto) <= MAX_RESULT_CHARS:
        return texto
    return texto[:MAX_RESULT_CHARS] + " …(recortado: pide algo más puntual si falta)"

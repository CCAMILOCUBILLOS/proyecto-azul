"""Puertos: los contratos que el núcleo espera de cada pieza externa.

Cada proveedor (Anthropic, Deepgram, SQLite…) se conecta mediante un adaptador
que cumple uno de estos contratos. Cambiar de proveedor es escribir otro
adaptador, sin tocar el núcleo (ADR 0008).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant"]


class Effort(StrEnum):
    """Cuánto debe pensar el cerebro (ADR 0014)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Message:
    role: Role
    text: str
    created_at: datetime | None = None
    # Lo que Azul consultó de verdad para esta respuesta ("búsqueda web; clima: …").
    consulted: str = ""


@dataclass(frozen=True)
class Fact:
    """Un dato importante sobre el usuario que Azul recuerda."""

    text: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class Usage:
    """Un consumo con costo, para el control de gasto (R3)."""

    provider: str
    cost_usd: float
    detail: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Una herramienta que el cerebro puede usar; el núcleo la ejecuta."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[str]]
    # Modo estricto: el proveedor garantiza que la entrada cumple el esquema. Tiene un
    # límite de tamaño total, así que se reserva para las herramientas que ejecutan
    # procesos; las demás validan su entrada por su cuenta.
    strict: bool = False


@dataclass(frozen=True)
class BrainRequest:
    system: str
    messages: list[Message]
    effort: Effort = Effort.MEDIUM
    # Información volátil (fecha y hora) que va al final para no romper la caché.
    context: str | None = None
    tools: list[ToolSpec] = field(default_factory=list)
    # Para trabajos internos (p. ej. clasificar correos, ADR 0039): sin búsqueda web y
    # sin una vuelta extra después de usar las herramientas. Abarata cada llamada.
    busqueda_web: bool = True
    terminar_tras_herramientas: bool = False


@dataclass(frozen=True)
class Searching:
    """El cerebro empezó a buscar en internet (para avisar y no dejar silencio)."""


# El cerebro emite trozos de texto a medida que responde, avisos y consumos con costo.
BrainEvent = str | Searching | Usage


class BrainError(Exception):
    """Fallo del cerebro, con un mensaje apto para mostrar al usuario."""


class VoiceError(Exception):
    """Fallo del oído o la voz, con un mensaje apto para mostrar al usuario."""


class WeatherError(Exception):
    """Fallo al consultar el clima, con un mensaje apto para el usuario."""


@dataclass(frozen=True)
class Transcript:
    text: str
    is_final: bool
    # El proveedor detectó que la persona dejó de hablar (silencio tras la frase).
    ends_speech: bool = False


class Brain(Protocol):
    """El cerebro: recibe la conversación y devuelve la respuesta por partes."""

    def respond(self, request: BrainRequest) -> AsyncIterator[BrainEvent]: ...

    async def prewarm(self, request: BrainRequest) -> Usage | None:
        """Prepara la caché del proveedor para que la próxima respuesta empiece antes."""
        ...


class SpeechToText(Protocol):
    """El oído: convierte audio en vivo (PCM 16 bits, mono) en texto."""

    def transcribe(self, audio: AsyncIterator[bytes]) -> AsyncIterator[Transcript | Usage]: ...


class TextToSpeech(Protocol):
    """La voz: convierte texto en audio (MP3)."""

    def synthesize(self, text: str) -> AsyncIterator[bytes | Usage]: ...


class WeatherProvider(Protocol):
    """El clima: estado actual y pronóstico de un lugar (ADR 0024)."""

    async def forecast(self, place: str, days: int) -> dict[str, Any]: ...


class RedNacionalError(Exception):
    """Fallo al hablar con el tablero de Red Nacional, con un mensaje apto para el usuario."""


class RedNacional(Protocol):
    """El tablero de Red Nacional de Confianza IPS, en el PC de Optometría (ADR 0031).

    Azul no hace el trabajo: le pide al tablero lo mismo que piden sus botones.
    """

    async def consultar(self, seccion: str, parametros: dict[str, str]) -> Any: ...

    async def ejecutar(self, operacion: str, datos: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class Habilidad:
    """Instrucciones para hacer bien un tipo de tarea (ADR 0032), en formato SKILL.md."""

    nombre: str
    descripcion: str
    instrucciones: str


class DocumentosError(Exception):
    """Fallo con un archivo, con un mensaje apto para el usuario."""


class Documentos(Protocol):
    """Los archivos del usuario en el portátil: buscar, leer, convertir y crear (ADR 0032).

    Nunca borra ni sobrescribe: lo que crea es siempre un archivo nuevo.
    """

    async def buscar(self, texto: str, extensiones: list[str]) -> list[dict[str, Any]]: ...

    async def leer(self, ruta: str) -> str: ...

    async def pdf_a_word(self, ruta: str) -> str: ...

    async def crear_word(self, titulo: str, contenido: str, modelo: str | None) -> str: ...

    async def crear_excel(self, titulo: str, hojas: list[dict[str, Any]]) -> str: ...

    async def guardar_archivo(self, nombre: str, extension: str, contenido: str) -> str: ...


class ArchivosError(Exception):
    """Fallo al manejar archivos o correr código, con un mensaje apto para el usuario."""


class Archivos(Protocol):
    """Los archivos de un equipo (portátil u Optometría) y correr Python allí (ADR 0041).

    Acciones: listar, buscar, leer, editar, escribir, restaurar, copiar, mover,
    crear_carpeta, papelera y python. Todo cambio deja copia de seguridad; nada se
    sobrescribe ni se borra del todo.
    """

    async def hacer(self, accion: str, entrada: dict[str, Any]) -> dict[str, Any]: ...


class CorreoError(Exception):
    """Fallo con el correo, con un mensaje apto para el usuario."""


class Correo(Protocol):
    """El correo del usuario: buscar y leer, y dejar borradores (ADR 0037).

    Nunca envía: lo que Azul redacta queda en Borradores y el usuario decide.
    """

    async def buscar(self, texto: str, carpeta: str, dias: int) -> list[dict[str, Any]]: ...

    async def leer(self, id_correo: str) -> dict[str, Any]: ...

    async def crear_borrador(
        self, para: list[str], cc: list[str], asunto: str, cuerpo: str, adjuntos: list[str]
    ) -> dict[str, Any]: ...

    async def responder_en_borrador(
        self, id_correo: str, cuerpo: str, a_todos: bool, adjuntos: list[str]
    ) -> dict[str, Any]: ...

    async def nuevos(self, desde: datetime, maximo: int) -> list[dict[str, Any]]:
        """Correos recibidos desde una fecha, del más nuevo al más viejo (ADR 0039)."""
        ...

    async def categorizar(self, prioridades: dict[str, str]) -> None:
        """Marca cada correo (id -> prioridad) con una categoría de color de Azul."""
        ...


class WhatsAppError(Exception):
    """Fallo al enviar por WhatsApp, con un mensaje apto para el usuario."""


@dataclass(frozen=True)
class MensajeEntrante:
    """Un mensaje que alguien le escribió al número de WhatsApp de Azul (ADR 0038)."""

    id: str
    de: str  # número internacional sin "+", como lo entrega WhatsApp
    nombre: str
    tipo: str  # "text", "audio", "image"…
    texto: str = ""


class WhatsApp(Protocol):
    """Enviar por el número de WhatsApp Business de Azul (ADR 0038)."""

    async def enviar(self, numero: str, texto: str) -> None: ...

    async def enviar_plantilla(self, numero: str, plantilla: str) -> None:
        """Un mensaje aprobado por Meta: lo único que se puede enviar pasadas 24 horas."""
        ...

    async def enviar_audio(self, numero: str, mp3: bytes) -> None:
        """Un audio (la voz de Azul) que se escucha dentro de WhatsApp."""
        ...


@dataclass(frozen=True)
class Regla:
    """Algo que el usuario le enseñó a Azul sobre un contacto de WhatsApp."""

    id: int
    contacto: str
    herramienta: str  # nombre de la herramienta, o "responder" (responder sin consultar)
    descripcion: str


@dataclass(frozen=True)
class Pendiente:
    """Una respuesta o un permiso que espera la decisión del usuario."""

    id: int
    contacto: str
    tipo: str  # "respuesta" o "permiso"
    texto: str  # lo que escribió el contacto
    propuesta: str = ""  # la respuesta que Azul propone
    herramienta: str = ""  # para los permisos


class VerificadorDeVoz(Protocol):
    """¿Quien habla es el usuario? Para que solo él pueda interrumpir a Azul (ADR 0036)."""

    @property
    def inscrito(self) -> bool: ...

    @property
    def muestras(self) -> int: ...

    async def agregar_muestra(self, pcm: bytes) -> int: ...

    async def terminar_inscripcion(self) -> None: ...

    async def borrar(self) -> None: ...

    async def es_el_usuario(self, pcm: bytes) -> bool: ...

    async def veredicto(self, pcm: bytes) -> str:
        """ "si", "no" o "dudoso" (conviene oír más voz antes de decidir)."""
        ...


class MemoryStore(Protocol):
    """La memoria: historial de conversación y datos sobre el usuario."""

    async def add_message(self, message: Message) -> None: ...

    async def recent_messages(self, limit: int) -> list[Message]: ...

    async def message_count(self) -> int: ...

    async def add_fact(self, fact: Fact) -> bool: ...

    async def facts(self) -> list[Fact]: ...


class MemoriaWhatsApp(Protocol):
    """Contactos, reglas aprendidas, pendientes e historial por contacto (ADR 0038)."""

    async def wa_marcar_visto(self, id_mensaje: str) -> bool:
        """True si el mensaje es nuevo (WhatsApp a veces entrega el mismo dos veces)."""
        ...

    async def wa_guardar_contacto(self, numero: str, nombre: str) -> None: ...

    async def wa_contactos(self) -> list[dict[str, Any]]: ...

    async def wa_ultimo_mensaje(self, numero: str) -> datetime | None: ...

    async def wa_reglas(self, contacto: str | None = None) -> list[Regla]: ...

    async def wa_agregar_regla(self, contacto: str, herramienta: str, descripcion: str) -> int: ...

    async def wa_borrar_regla(self, id_regla: int) -> bool: ...

    async def wa_nuevo_pendiente(self, pendiente: Pendiente) -> int: ...

    async def wa_pendientes(self) -> list[Pendiente]: ...

    async def wa_cerrar_pendiente(self, id_pendiente: int, estado: str) -> Pendiente | None: ...

    def memoria_de(self, contacto: str) -> "MemoriaDeContacto": ...


class MemoriaDeContacto(MemoryStore, Protocol):
    """El historial con un contacto; los datos son los del usuario más los del contacto."""

    async def corregir_ultima_respuesta(self, texto: str | None) -> None:
        """Cambia (o borra, con None) la última respuesta guardada, si no se envió tal cual."""
        ...


class MemoriaBandeja(Protocol):
    """Lo que Azul sabe de los correos del usuario: clasificación, reglas, itinerario (ADR 0039)."""

    async def bandeja_ya_vistos(self, ids: list[str]) -> set[str]: ...

    async def bandeja_guardar(self, clasificados: list[dict[str, Any]]) -> None: ...

    async def bandeja_numero(self, id_correo: str) -> int | None: ...

    async def bandeja_itinerario(self, limite: int) -> list[dict[str, Any]]: ...

    async def bandeja_marcar(self, numero: int, estado: str) -> bool: ...

    async def bandeja_cambiar_prioridad(
        self, numero: int, prioridad: str
    ) -> dict[str, Any] | None: ...

    async def bandeja_reglas(self) -> list[dict[str, Any]]: ...

    async def bandeja_agregar_regla(self, criterio: str, prioridad: str) -> int: ...

    async def bandeja_borrar_regla(self, id_regla: int) -> bool: ...

    async def bandeja_nueva_pregunta(self, numero: int, pregunta: str) -> int: ...

    async def bandeja_preguntas(self) -> list[dict[str, Any]]: ...

    async def bandeja_cerrar_pregunta(self, id_pregunta: int) -> dict[str, Any] | None: ...

    async def bandeja_estado(self, clave: str) -> str | None: ...

    async def bandeja_guardar_estado(self, clave: str, valor: str) -> None: ...


class UsageMeter(Protocol):
    """El medidor de gasto mensual."""

    async def record(self, usage: Usage) -> None: ...

    async def month_total_usd(self) -> float: ...

"""Configuración de Azul.

Todo valor configurable vive aquí y se lee de variables de entorno o del archivo
`.env` en la raíz del proyecto. Nunca se escriben claves en el código.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# nucleo/src/azul/config.py -> raíz del proyecto
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AZUL_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        # Una línea vacía en .env (p. ej. "ANTHROPIC_API_KEY=") cuenta como no configurada.
        env_ignore_empty=True,
        extra="ignore",
    )

    # Servidor. Solo escucha en el propio equipo; Tailscale publica el acceso
    # seguro hacia tus dispositivos (ADR 0003).
    host: str = "127.0.0.1"
    port: int = 8710

    # Carpeta con todos los datos de Azul: copiarla es migrar (R1, ADR 0009).
    data_dir: Path = REPO_ROOT / "datos"
    # App web ya compilada, servida por el mismo núcleo.
    app_dist_dir: Path = REPO_ROOT / "app" / "dist"

    # Secretos (ADR 0012). Las claves de proveedores usan sus nombres estándar.
    access_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    deepgram_api_key: SecretStr | None = Field(default=None, validation_alias="DEEPGRAM_API_KEY")

    # Cerebro (ADR 0005, 0014, 0015).
    # Mezcla de modelos (ADR 0030): lo cotidiano con Sonnet; "piénsalo a fondo" con Opus.
    brain_model: str = "claude-sonnet-5-5"
    brain_model_deep: str = "claude-opus-5-5"
    # Funciones beta de Anthropic; se pueden apagar si el proveedor las rechaza.
    anthropic_fallbacks: bool = True
    anthropic_per_message_effort: bool = True
    # Cada búsqueda tarda 8-12 s: 2 como máximo por respuesta (antes 3).
    web_search_max_uses: int = Field(default=2, ge=0)
    # Tablero de Red Nacional en el PC de Optometría, por Tailscale (ADR 0031).
    # Vacío: Azul no ofrece esas herramientas.
    red_nacional_url: str = ""
    # Habilidades y archivos del usuario (ADR 0032).
    habilidades_dir: Path = REPO_ROOT / "habilidades"
    documentos_activos: bool = True
    documentos_salida: Path = Field(default_factory=lambda: _onedrive_dir("Documentos"))
    # Outlook clásico del portátil: buscar, leer y dejar borradores; nunca envía (ADR 0037).
    correo_activo: bool = True
    # El Outlook real está en el PC de Optometría: su ayudante, por Tailscale (ADR 0040).
    # Con esto, Azul usa ese Outlook en vez del de este equipo.
    correo_remoto_url: str = ""
    correo_remoto_clave: SecretStr | None = None
    # Editar, organizar y correr Python, solo para el usuario (ADR 0041).
    archivos_activos: bool = True
    archivos_respaldos: Path = Field(default_factory=lambda: _onedrive_dir("Respaldos de archivos"))
    archivos_trabajo: Path = Field(default_factory=lambda: _onedrive_dir("Trabajo"))
    # Firma de Outlook para los correos que redacta Azul (su nombre en Outlook).
    correo_firma: str = ""
    # Revisión de correos: prioridades, itinerario y alertas de lo urgente (ADR 0039).
    correo_revisar: bool = True
    correo_revision_minutos: float = Field(default=10, ge=2)
    # WhatsApp Business de Meta (ADR 0038). Sin token ni número, Azul no lo usa.
    whatsapp_token: SecretStr | None = None
    whatsapp_numero_id: str = ""  # el "Phone number ID" de Meta (no es el teléfono)
    whatsapp_secreto_app: SecretStr | None = None  # para comprobar que los avisos son de Meta
    whatsapp_token_verificacion: SecretStr | None = None  # una frase que el usuario inventa
    whatsapp_dueno: str = ""  # el número personal del usuario, p. ej. 573001234567
    whatsapp_plantilla_aviso: str = ""  # plantilla aprobada para avisar pasadas 24 h
    whatsapp_puerto: int = 8720  # solo el receptor de WhatsApp; Tailscale Funnel lo publica
    whatsapp_api_version: str = "v23.0"

    # Oído y voz (ADR 0006). Voz elegida por el usuario el 2026-10-05: Gloria (colombiana).
    stt_model: str = "nova-3"
    stt_language: str = "es"
    tts_voice: str = "aura-2-gloria-es"

    # Control de gasto (R3).
    monthly_budget_usd: float = Field(default=50.0, gt=0)
    budget_warning_usd: float = Field(default=40.0, gt=0)

    # Cliente de voz del portátil (ADR 0028): atajo siempre; "Oye Azul" solo en horario.
    escritorio_activo: bool = True
    escritorio_atajo: str = "<ctrl>+<alt>+a"
    escritorio_oye_azul: bool = True
    # Todo el día por decisión del usuario (ADR 0035): esperar ya no cuesta nada.
    escritorio_desde: str = "00:00"
    escritorio_hasta: str = "00:00"
    escritorio_modelo_voz: Path = REPO_ROOT / "datos" / "modelos" / "vosk-model-small-es-0.42"
    # Huella de voz para interrumpir a Azul solo con la voz del usuario (ADR 0036).
    modelo_hablantes: Path = REPO_ROOT / "datos" / "modelos" / "vosk-model-spk-0.4"

    # Respaldos de la memoria (ADR 0022): en el portátil y en OneDrive, por decisión
    # del usuario. Sin OneDrive, solo en el portátil.
    backup_dir: Path = REPO_ROOT / "respaldos"
    backup_cloud_dir: Path | None = Field(default_factory=lambda: _onedrive_backup_dir())
    backups_to_keep: int = Field(default=14, ge=1)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "azul.db"

    @property
    def backup_destinations(self) -> list[Path]:
        return [self.backup_dir, *([self.backup_cloud_dir] if self.backup_cloud_dir else [])]

    @model_validator(mode="after")
    def _warning_below_budget(self) -> "Settings":
        if self.budget_warning_usd >= self.monthly_budget_usd:
            raise ValueError("budget_warning_usd debe ser menor que monthly_budget_usd")
        return self


def _onedrive_dir(subcarpeta: str) -> Path:
    """OneDrive/Azul/<subcarpeta>; sin OneDrive, la carpeta Documentos del usuario."""
    onedrive = os.environ.get("ONEDRIVE")
    base = Path(onedrive) / "Azul" if onedrive else Path.home() / "Documents" / "Azul"
    return base / subcarpeta


def _onedrive_backup_dir() -> Path | None:
    # En Windows las variables de entorno no distinguen mayúsculas ("OneDrive").
    onedrive = os.environ.get("ONEDRIVE")
    return Path(onedrive) / "Azul" / "respaldos" if onedrive else None


@lru_cache
def get_settings() -> Settings:
    return Settings()

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
    brain_model: str = "claude-opus-5-5"
    # Funciones beta de Anthropic; se pueden apagar si el proveedor las rechaza.
    anthropic_fallbacks: bool = True
    anthropic_per_message_effort: bool = True
    # Cada búsqueda tarda 8-12 s: 2 como máximo por respuesta (antes 3).
    web_search_max_uses: int = Field(default=2, ge=0)

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
    escritorio_desde: str = "07:00"
    escritorio_hasta: str = "22:00"

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


def _onedrive_backup_dir() -> Path | None:
    # En Windows las variables de entorno no distinguen mayúsculas ("OneDrive").
    onedrive = os.environ.get("ONEDRIVE")
    return Path(onedrive) / "Azul" / "respaldos" if onedrive else None


@lru_cache
def get_settings() -> Settings:
    return Settings()

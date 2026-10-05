"""Configuración de Azul.

Todo valor configurable vive aquí y se lee de variables de entorno o del archivo
`.env` en la raíz del proyecto. Nunca se escriben claves en el código.
"""

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
    web_search_max_uses: int = Field(default=3, ge=0)

    # Control de gasto (R3).
    monthly_budget_usd: float = Field(default=50.0, gt=0)
    budget_warning_usd: float = Field(default=40.0, gt=0)

    @model_validator(mode="after")
    def _warning_below_budget(self) -> "Settings":
        if self.budget_warning_usd >= self.monthly_budget_usd:
            raise ValueError("budget_warning_usd debe ser menor que monthly_budget_usd")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

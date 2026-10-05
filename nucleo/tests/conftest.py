import pytest

from azul.config import Settings

ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "DEEPGRAM_API_KEY",
    "AZUL_HOST",
    "AZUL_PORT",
    "AZUL_DATA_DIR",
    "AZUL_APP_DIST_DIR",
    "AZUL_ACCESS_KEY",
    "AZUL_BRAIN_MODEL",
    "AZUL_MONTHLY_BUDGET_USD",
    "AZUL_BUDGET_WARNING_USD",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Aísla las pruebas de las variables de entorno reales del equipo."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Configuración de prueba: sin .env real y con carpetas temporales."""
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "datos",
        app_dist_dir=tmp_path / "dist",
    )

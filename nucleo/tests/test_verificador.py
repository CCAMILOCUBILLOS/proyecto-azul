import pytest

from azul.adapters.verificador_vosk import VerificadorVosk, cargar_verificador

pytestmark = pytest.mark.anyio

USUARIO = [1.0, 0.0, 0.0]
AZUL = [0.0, 1.0, 0.0]


class VerificadorDePrueba(VerificadorVosk):
    """Sin modelos: cada "audio" ya trae su vector (los bytes eligen cuál)."""

    vectores = {
        b"usuario": [0.9, 0.1, 0.05],
        b"otro": [0.2, 0.2, 0.9],
        b"eco": [0.3, 0.9, 0.0],
        b"usuario con eco": [0.6, 0.6, 0.0],
    }

    async def _vector(self, pcm):
        return self.vectores.get(pcm)


def verificador(tmp_path, huella_azul=AZUL):
    v = VerificadorDePrueba(tmp_path, tmp_path, tmp_path / "huella.json", tmp_path / "azul.json")
    v._huella_azul = huella_azul
    return v


async def test_enrollment_saves_only_the_numeric_print(tmp_path):
    v = verificador(tmp_path)
    for _ in range(3):
        await v.agregar_muestra(b"usuario")

    await v.terminar_inscripcion()

    assert v.inscrito
    assert (tmp_path / "huella.json").read_text(encoding="utf-8").startswith("[0.9")
    nuevo = VerificadorDePrueba(
        tmp_path, tmp_path, tmp_path / "huella.json", tmp_path / "azul.json"
    )
    assert nuevo.inscrito


async def test_needs_three_samples_and_enough_voice(tmp_path):
    v = verificador(tmp_path)
    with pytest.raises(ValueError, match="suficiente voz"):
        await v.agregar_muestra(b"silencio")
    await v.agregar_muestra(b"usuario")
    with pytest.raises(ValueError, match="3 frases"):
        await v.terminar_inscripcion()


async def test_accepts_the_user_and_rejects_others_and_azul_echo(tmp_path):
    v = verificador(tmp_path)
    v._huella = USUARIO

    assert await v.es_el_usuario(b"usuario")
    assert not await v.es_el_usuario(b"otro")
    assert not await v.es_el_usuario(b"eco")
    # Se parece al usuario, pero casi igual a Azul: no alcanza el margen.
    assert not await v.es_el_usuario(b"usuario con eco")


async def test_a_middling_resemblance_is_doubtful(tmp_path):
    v = verificador(tmp_path)
    v._huella = USUARIO
    v.vectores = {**v.vectores, b"parecido": [0.4, 0.05, 0.9]}

    assert await v.veredicto(b"parecido") == "dudoso"
    assert not await v.es_el_usuario(b"parecido")


async def test_without_enrollment_nobody_interrupts(tmp_path):
    assert not await verificador(tmp_path).es_el_usuario(b"usuario")


async def test_forgetting_the_voice_deletes_the_print(tmp_path):
    v = verificador(tmp_path)
    for _ in range(3):
        await v.agregar_muestra(b"usuario")
    await v.terminar_inscripcion()

    await v.borrar()

    assert not v.inscrito
    assert not (tmp_path / "huella.json").exists()


def test_not_available_without_models(tmp_path):
    assert cargar_verificador(tmp_path / "no", tmp_path / "no", tmp_path) is None

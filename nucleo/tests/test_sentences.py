from azul.core.sentences import SentenceSplitter


def test_emits_sentences_as_they_complete():
    splitter = SentenceSplitter()

    assert splitter.feed("Hola. ¿Qué") == ["Hola."]
    assert splitter.feed(" tal estás? Bien") == ["¿Qué tal estás?"]
    assert splitter.flush() == "Bien"
    assert splitter.flush() is None


def test_keeps_decimals_and_handles_exclamations():
    splitter = SentenceSplitter()

    assert splitter.feed("Hace 21.5 grados. ¡Qué") == ["Hace 21.5 grados."]
    assert splitter.feed(" frío!\nAbrígate") == ["¡Qué frío!"]
    assert splitter.flush() == "Abrígate"

from azul.core.notes import FactNotes


def test_removes_notes_and_collects_facts():
    notes = FactNotes()

    visible, facts = notes.feed(
        "¡Mucho gusto, Camilo! <recordar>El usuario se llama Camilo.</recordar>"
    )

    assert visible == "¡Mucho gusto, Camilo!"
    assert facts == ["El usuario se llama Camilo."]
    assert notes.flush() == ""


def test_handles_notes_split_across_chunks():
    notes = FactNotes()
    chunks = ["Anotado. <rec", "ordar>Le gusta el ", "café.</reco", "rdar> ¿Algo más?"]

    results = [notes.feed(chunk) for chunk in chunks]

    assert "".join(v for v, _ in results) + notes.flush() == "Anotado. ¿Algo más?"
    assert [f for _, fs in results for f in fs] == ["Le gusta el café."]


def test_text_that_only_looks_like_a_tag_is_kept():
    notes = FactNotes()

    visible, facts = notes.feed("Usa el signo <")
    rest = notes.flush()

    assert visible + rest == "Usa el signo <"
    assert facts == []


def test_several_notes_and_unclosed_note_is_dropped():
    notes = FactNotes()

    visible, facts = notes.feed(
        "Hola<recordar>A.</recordar> y<recordar>B.</recordar><recordar>sin ci"
    )

    assert visible == "Hola y"
    assert facts == ["A.", "B."]
    assert notes.flush() == ""


def test_blank_lines_before_a_note_are_dropped():
    notes = FactNotes()

    parts = [notes.feed(c) for c in ["¿En qué te ayudo?", "\n\n", "<recordar>Dato.</recordar>"]]

    assert "".join(v for v, _ in parts) + notes.flush() == "¿En qué te ayudo?"


def test_spaces_between_words_are_kept():
    notes = FactNotes()

    parts = [notes.feed(c) for c in ["Hace ", "sol ", "hoy."]]

    assert "".join(v for v, _ in parts) + notes.flush() == "Hace sol hoy."

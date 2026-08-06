import pytest

from app.services.rag import _cosine_similarity, chunk_text


def test_chunk_text_splits_long_text():
    text = "A" * 2000
    chunks = chunk_text(text, chunk_size=800, overlap=100)

    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)


def test_chunk_text_returns_single_chunk_for_short_text():
    text = "Short note."
    chunks = chunk_text(text, chunk_size=800, overlap=100)

    assert chunks == ["Short note."]


def test_chunk_text_returns_empty_list_for_blank_input():
    assert chunk_text("   ") == []
    assert chunk_text("") == []


def test_cosine_similarity_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_does_not_crash():
    assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
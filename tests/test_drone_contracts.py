from __future__ import annotations

from aura.drones.contracts import (
    BUILTIN_TYPES,
    ArtifactType,
    is_compatible,
)

# ── is_compatible ──────────────────────────────────────────────────


def test_is_compatible_exact_match() -> None:
    """Two identical schemas are compatible."""
    producer = ArtifactType(name="A", schema={"x": "string", "y": "number"})
    consumer = ArtifactType(name="B", schema={"x": "string", "y": "number"})
    assert is_compatible(producer, consumer) is True


def test_is_compatible_producer_extra_fields() -> None:
    """Producer with superset fields is still compatible (width is fine)."""
    producer = ArtifactType(name="A", schema={"x": "string", "y": "number", "z": "bool"})
    consumer = ArtifactType(name="B", schema={"x": "string", "y": "number"})
    assert is_compatible(producer, consumer) is True


def test_is_compatible_missing_field() -> None:
    """Consumer requires a field the producer lacks → incompatible."""
    producer = ArtifactType(name="A", schema={"x": "string"})
    consumer = ArtifactType(name="B", schema={"x": "string", "y": "number"})
    assert is_compatible(producer, consumer) is False


def test_is_compatible_type_mismatch() -> None:
    """Same field, different types → incompatible."""
    producer = ArtifactType(name="A", schema={"x": "number"})
    consumer = ArtifactType(name="B", schema={"x": "string"})
    assert is_compatible(producer, consumer) is False


def test_is_compatible_any_accepts_anything() -> None:
    """A producer field with type 'any' matches any consumer type."""
    producer = ArtifactType(name="A", schema={"x": "any", "y": "string"})
    consumer = ArtifactType(name="B", schema={"x": "number", "y": "string"})
    assert is_compatible(producer, consumer) is True

    producer2 = ArtifactType(name="A", schema={"x": "any"})
    consumer2 = ArtifactType(name="B", schema={"x": "list"})
    assert is_compatible(producer2, consumer2) is True


def test_is_compatible_consumer_any_accepts_anything() -> None:
    """A consumer field with type 'any' accepts any producer type."""
    producer = ArtifactType(name="A", schema={"x": "number"})
    consumer = ArtifactType(name="B", schema={"x": "any"})
    assert is_compatible(producer, consumer) is True

    producer2 = ArtifactType(name="A", schema={"x": "bool"})
    consumer2 = ArtifactType(name="B", schema={"x": "any"})
    assert is_compatible(producer2, consumer2) is True


def test_is_compatible_empty_consumer() -> None:
    """Consumer with no fields is vacuously compatible."""
    producer = ArtifactType(name="A", schema={"x": "string", "y": "number"})
    consumer = ArtifactType(name="B", schema={})
    assert is_compatible(producer, consumer) is True

    producer2 = ArtifactType(name="A", schema={})
    consumer2 = ArtifactType(name="B", schema={})
    assert is_compatible(producer2, consumer2) is True


# ── BUILTIN_TYPES registry ────────────────────────────────────────


def test_builtin_types_registry() -> None:
    """BUILTIN_TYPES contains all 5 names, each is an ArtifactType."""
    expected_names = {"SearchBrief", "OpportunityBatch", "FitReview", "ReplyDrafts", "PostingLog"}
    assert set(BUILTIN_TYPES.keys()) == expected_names
    for name in expected_names:
        at = BUILTIN_TYPES[name]
        assert isinstance(at, ArtifactType)
        assert at.name == name
        assert isinstance(at.schema, dict)


def test_builtin_types_are_distinct() -> None:
    """Each builtin type has a unique name."""
    names = [t.name for t in BUILTIN_TYPES.values()]
    assert len(names) == len(set(names))

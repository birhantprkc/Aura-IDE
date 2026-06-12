"""Tests for aura.drones.chain — chain data model, validation, and store."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from aura import paths as aura_paths
from aura.drones.chain import (
    ChainDefinition,
    ChainEdge,
    ChainNode,
    ChainValidation,
    topological_order,
    validate,
)
from aura.drones.chain_store import ChainStore, _chain_from_dict
from aura.drones.definition import DroneDefinition

# ── Helpers ─────────────────────────────────────────────────────────


def _make_drone(
    drone_id: str,
    name: str = "",
    accepts: str = "",
    produces: str = "",
    enabled: bool = True,
) -> DroneDefinition:
    return DroneDefinition(
        id=drone_id,
        name=name or drone_id,
        description="",
        instructions="Do the thing",
        write_policy="read_only",
        allowed_tools=(),
        output_contract="Output",
        enabled=enabled,
        accepts=accepts,
        produces=produces,
    )


# ── Data model round-trip ──────────────────────────────────────────


def test_chain_definition_roundtrip() -> None:
    """Create a ChainDefinition, serialize via asdict, reconstruct, assert equal."""
    chain = ChainDefinition(
        id="test-chain",
        name="Test Chain",
        description="A test chain for round-trip",
        nodes=(
            ChainNode(
                id="n1",
                drone_id="drone-a",
                goal_template="search {{query}}",
                position=(100.0, 200.0),
            ),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
        created_at="2025-01-01T00:00:00",
        updated_at="2025-01-02T00:00:00",
        schedule="0 0 * * *",
    )
    data = asdict(chain)
    reconstructed = _chain_from_dict(data)
    assert reconstructed == chain


def test_chain_definition_empty_nodes_edges() -> None:
    """A chain with no nodes or edges round-trips correctly."""
    chain = ChainDefinition(
        id="empty",
        name="Empty",
        description="An empty chain",
    )
    data = asdict(chain)
    reconstructed = _chain_from_dict(data)
    assert reconstructed == chain
    assert reconstructed.nodes == ()
    assert reconstructed.edges == ()


def test_chain_definition_default_fields() -> None:
    """Default field values are set correctly."""
    chain = ChainDefinition(
        id="defaults",
        name="Defaults",
        description="Default field chain",
    )
    assert chain.nodes == ()
    assert chain.edges == ()
    assert chain.created_at == ""
    assert chain.updated_at == ""
    assert chain.enabled is True
    assert chain.schedule == ""


# ── ChainValidation ────────────────────────────────────────────────


def test_chain_validation_fresh() -> None:
    """A fresh ChainValidation has ok=False and empty errors."""
    v = ChainValidation()
    assert v.ok is False
    assert v.errors == []


def test_chain_validation_with_errors() -> None:
    """ChainValidation with errors has ok=False."""
    v = ChainValidation(ok=False, errors=["error 1"])
    assert v.ok is False
    assert v.errors == ["error 1"]


def test_chain_validation_ok() -> None:
    """ChainValidation with ok=True and no errors."""
    v = ChainValidation(ok=True)
    assert v.ok is True
    assert v.errors == []


# ── topological_order ──────────────────────────────────────────────


def test_topological_order_simple() -> None:
    """A linear chain produces ids in order."""
    chain = ChainDefinition(
        id="linear",
        name="Linear",
        description="",
        nodes=(
            ChainNode(id="a", drone_id="d1"),
            ChainNode(id="b", drone_id="d2"),
            ChainNode(id="c", drone_id="d3"),
        ),
        edges=(
            ChainEdge(from_node="a", to_node="b"),
            ChainEdge(from_node="b", to_node="c"),
        ),
    )
    order = topological_order(chain)
    assert order == ["a", "b", "c"]


def test_topological_order_branching() -> None:
    """A DAG with branches produces a valid topological order."""
    chain = ChainDefinition(
        id="branching",
        name="Branching",
        description="",
        nodes=(
            ChainNode(id="a", drone_id="d1"),
            ChainNode(id="b", drone_id="d2"),
            ChainNode(id="c", drone_id="d3"),
        ),
        edges=(
            ChainEdge(from_node="a", to_node="b"),
            ChainEdge(from_node="a", to_node="c"),
        ),
    )
    order = topological_order(chain)
    assert order[0] == "a"
    assert set(order[1:]) == {"b", "c"}


def test_topological_order_disconnected() -> None:
    """Disconnected sub-graphs are topologically orderable."""
    chain = ChainDefinition(
        id="disconnected",
        name="Disconnected",
        description="",
        nodes=(
            ChainNode(id="a", drone_id="d1"),
            ChainNode(id="b", drone_id="d2"),
            ChainNode(id="c", drone_id="d3"),
        ),
        edges=(
            ChainEdge(from_node="a", to_node="b"),
        ),
    )
    order = topological_order(chain)
    assert order[0] == "a" or order[0] == "c"
    assert len(order) == 3


def test_topological_order_cycle() -> None:
    """A cycle raises ValueError."""
    chain = ChainDefinition(
        id="cycle",
        name="Cycle",
        description="",
        nodes=(
            ChainNode(id="a", drone_id="d1"),
            ChainNode(id="b", drone_id="d2"),
            ChainNode(id="c", drone_id="d3"),
        ),
        edges=(
            ChainEdge(from_node="a", to_node="b"),
            ChainEdge(from_node="b", to_node="c"),
            ChainEdge(from_node="c", to_node="a"),
        ),
    )
    with pytest.raises(ValueError, match="Cycle detected"):
        topological_order(chain)


# ── validate — passing ─────────────────────────────────────────────


def test_validate_passing() -> None:
    """A valid chain with compatible types passes."""
    drone_a = _make_drone("drone-a", produces="SearchBrief")
    drone_b = _make_drone("drone-b", accepts="SearchBrief")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="passing",
        name="Passing Chain",
        description="Passes validation",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is True
    assert result.errors == []


def test_validate_passing_single_node() -> None:
    """A single-node chain (no edges) passes validation."""
    drone = _make_drone("drone-a")
    lookup = {"drone-a": drone}

    chain = ChainDefinition(
        id="single",
        name="Single Node",
        description="Just one node",
        nodes=(ChainNode(id="n1", drone_id="drone-a"),),
    )

    result = validate(chain, lookup)
    assert result.ok is True


# ── validate — no start node ───────────────────────────────────────


def test_validate_no_start_node() -> None:
    """A chain where every node has an inbound edge has no start node."""
    drone = _make_drone("drone-a")
    lookup = {"drone-a": drone}

    chain = ChainDefinition(
        id="no-start",
        name="No Start",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-a"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
            ChainEdge(from_node="n2", to_node="n1"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    assert any("no start node" in e.lower() for e in result.errors)


# ── validate — missing drone_id ────────────────────────────────────


def test_validate_missing_drone_id() -> None:
    """A node referencing a drone not in lookup fails."""
    drone_b = _make_drone("drone-b")
    lookup = {"drone-b": drone_b}

    chain = ChainDefinition(
        id="missing",
        name="Missing Drone",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    assert any("drone-a" in e for e in result.errors)
    assert any("n1" in e for e in result.errors)


# ── validate — disabled drone ──────────────────────────────────────


def test_validate_disabled_drone() -> None:
    """A node referencing a disabled drone fails."""
    drone_a = _make_drone("drone-a", enabled=False)
    drone_b = _make_drone("drone-b")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="disabled",
        name="Disabled Drone",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    assert any("disabled" in e.lower() for e in result.errors)


# ── validate — cycle ───────────────────────────────────────────────


def test_validate_cycle() -> None:
    """A chain with a cycle fails validation."""
    drone = _make_drone("drone-a")
    lookup = {"drone-a": drone}

    chain = ChainDefinition(
        id="cycle-chain",
        name="Cycle Chain",
        description="",
        nodes=(
            ChainNode(id="a", drone_id="drone-a"),
            ChainNode(id="b", drone_id="drone-a"),
            ChainNode(id="c", drone_id="drone-a"),
        ),
        edges=(
            ChainEdge(from_node="a", to_node="b"),
            ChainEdge(from_node="b", to_node="c"),
            ChainEdge(from_node="c", to_node="a"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    assert any("cycle" in e.lower() for e in result.errors)


# ── validate — type incompatible ───────────────────────────────────


def test_validate_type_incompatible() -> None:
    """Edge with incompatible types fails with a message naming both types."""
    drone_a = _make_drone("drone-a", produces="SearchBrief")
    drone_b = _make_drone("drone-b", accepts="FitReview")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="type-mismatch",
        name="Type Mismatch",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    type_errors = [e for e in result.errors if "type mismatch" in e]
    assert len(type_errors) >= 1
    assert "SearchBrief" in type_errors[0]
    assert "FitReview" in type_errors[0]


# ── validate — free-form interop ───────────────────────────────────


def test_validate_free_form_both_empty() -> None:
    """Both producer and consumer free-form passes."""
    drone_a = _make_drone("drone-a", produces="")
    drone_b = _make_drone("drone-b", accepts="")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="free-both",
        name="Free Both",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is True


def test_validate_free_form_producer_typed_consumer_free() -> None:
    """Producer with typed output, consumer free-form — passes."""
    drone_a = _make_drone("drone-a", produces="SearchBrief")
    drone_b = _make_drone("drone-b", accepts="")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="typed-to-free",
        name="Typed to Free",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is True


def test_validate_free_form_producer_free_consumer_typed() -> None:
    """Producer free-form, consumer requires typed — fails."""
    drone_a = _make_drone("drone-a", produces="")
    drone_b = _make_drone("drone-b", accepts="OpportunityBatch")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="free-to-typed",
        name="Free to Typed",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    assert any("no produces type" in e for e in result.errors)


# ── ChainStore round-trip ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point data_dir to a tmp_path subdirectory for test isolation."""
    monkeypatch.setattr(aura_paths, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr("aura.drones.chain_store.data_dir", lambda: tmp_path / "data")


def test_chain_store_save_and_load(tmp_path: Path) -> None:
    """Save a chain, load it back, assert equality."""
    chain = ChainDefinition(
        id="my-chain",
        name="My Chain",
        description="A test chain",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    ChainStore.save_chain(tmp_path, chain)
    loaded = ChainStore.load_chain(tmp_path, "my-chain")
    assert loaded is not None
    assert loaded == chain


def test_chain_store_list_chains(tmp_path: Path) -> None:
    """List returns saved chains sorted by name."""
    chain_b = ChainDefinition(
        id="chain-b", name="Beta", description="Second chain"
    )
    chain_a = ChainDefinition(
        id="chain-a", name="Alpha", description="First chain"
    )
    ChainStore.save_chain(tmp_path, chain_b)
    ChainStore.save_chain(tmp_path, chain_a)

    chains = ChainStore.list_chains(tmp_path)
    assert len(chains) == 2
    assert chains[0].name == "Alpha"
    assert chains[1].name == "Beta"


def test_chain_store_list_empty(tmp_path: Path) -> None:
    """list_chains returns empty list when no chains exist."""
    assert ChainStore.list_chains(tmp_path) == []


def test_chain_store_delete(tmp_path: Path) -> None:
    """Delete a chain, verify it's gone."""
    chain = ChainDefinition(
        id="to-delete",
        name="Delete Me",
        description="Will be deleted",
    )
    ChainStore.save_chain(tmp_path, chain)
    assert ChainStore.load_chain(tmp_path, "to-delete") is not None

    deleted = ChainStore.delete_chain(tmp_path, "to-delete")
    assert deleted is True
    assert ChainStore.load_chain(tmp_path, "to-delete") is None
    assert ChainStore.list_chains(tmp_path) == []


def test_chain_store_delete_nonexistent(tmp_path: Path) -> None:
    """Deleting a nonexistent chain returns False."""
    assert ChainStore.delete_chain(tmp_path, "does-not-exist") is False


def test_chain_store_save_creates_directory(tmp_path: Path) -> None:
    """Saving a chain creates the chain directory and chain.json."""
    chain = ChainDefinition(
        id="first-chain",
        name="First Chain",
        description="First chain for testing",
    )
    ChainStore.save_chain(tmp_path, chain)

    chain_dir = ChainStore.chains_dir() / "first-chain"
    assert chain_dir.exists()
    assert (chain_dir / "chain.json").exists()


def test_chain_store_save_updates_existing(tmp_path: Path) -> None:
    """Saving with the same id overwrites the existing chain."""
    original = ChainDefinition(
        id="update-me",
        name="Original",
        description="Original description",
    )
    ChainStore.save_chain(tmp_path, original)

    updated = ChainDefinition(
        id="update-me",
        name="Updated",
        description="Updated description",
        nodes=(ChainNode(id="n1", drone_id="drone-a"),),
    )
    ChainStore.save_chain(tmp_path, updated)

    loaded = ChainStore.load_chain(tmp_path, "update-me")
    assert loaded is not None
    assert loaded.name == "Updated"
    assert loaded.description == "Updated description"
    assert len(loaded.nodes) == 1


def test_chain_store_load_nonexistent(tmp_path: Path) -> None:
    """load_chain returns None for nonexistent chains."""
    assert ChainStore.load_chain(tmp_path, "no-such-chain") is None


def test_chain_store_load_invalid_id(tmp_path: Path) -> None:
    """load_chain returns None for invalid chain ids."""
    assert ChainStore.load_chain(tmp_path, "../evil") is None


# ── ChainStore next_id ─────────────────────────────────────────────


def test_chain_store_next_id_basic(tmp_path: Path) -> None:
    """next_id generates a slug from the name."""
    assert ChainStore.next_id(tmp_path, "Release Chain") == "release-chain"


def test_chain_store_next_id_duplicate(tmp_path: Path) -> None:
    """next_id appends -1 when the id already exists."""
    chain = ChainDefinition(
        id="release-chain",
        name="Release Chain",
        description="A release chain",
    )
    ChainStore.save_chain(tmp_path, chain)
    assert ChainStore.next_id(tmp_path, "Release Chain") == "release-chain-1"


def test_chain_store_next_id_multiple_duplicates(tmp_path: Path) -> None:
    """next_id increments correctly with multiple existing ids."""
    for i in range(4):
        cid = f"my-chain-{i}" if i > 0 else "my-chain"
        chain = ChainDefinition(
            id=cid,
            name=f"My Chain {i}",
            description=f"Chain number {i}",
        )
        ChainStore.save_chain(tmp_path, chain)

    assert ChainStore.next_id(tmp_path, "My Chain") == "my-chain-4"


# ── ChainStore validate_chain ──────────────────────────────────────


def test_validate_chain_rejects_empty_id(tmp_path: Path) -> None:
    """validate_chain raises ValueError for invalid chain id."""
    chain = ChainDefinition(
        id="",
        name="Test",
        description="Test chain",
    )
    with pytest.raises(ValueError, match="Chain id must be"):
        ChainStore.validate_chain(chain)


def test_validate_chain_rejects_empty_name(tmp_path: Path) -> None:
    """validate_chain raises ValueError for empty name."""
    chain = ChainDefinition(
        id="test-chain",
        name="",
        description="Test chain",
    )
    with pytest.raises(ValueError, match="Chain name is required"):
        ChainStore.validate_chain(chain)


def test_validate_chain_rejects_empty_description(tmp_path: Path) -> None:
    """validate_chain raises ValueError for empty description."""
    chain = ChainDefinition(
        id="test-chain",
        name="Test",
        description="",
    )
    with pytest.raises(ValueError, match="Chain description is required"):
        ChainStore.validate_chain(chain)


def test_validate_chain_accepts_valid(tmp_path: Path) -> None:
    """A valid chain passes validate_chain without error."""
    chain = ChainDefinition(
        id="valid-chain",
        name="Valid Chain",
        description="A valid chain",
    )
    # Should not raise
    ChainStore.validate_chain(chain)


# ── Error message clarity ──────────────────────────────────────────


def test_validate_message_names_both_types() -> None:
    """Incompatible type error message names both types."""
    drone_a = _make_drone("drone-a", produces="SearchBrief")
    drone_b = _make_drone("drone-b", accepts="FitReview")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="msg-test",
        name="Message Test",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    match = [e for e in result.errors if "type mismatch" in e]
    assert len(match) >= 1
    assert "SearchBrief" in match[0]
    assert "FitReview" in match[0]


def test_validate_message_no_produces_type() -> None:
    """Error when producer has no type but consumer requires one."""
    drone_a = _make_drone("drone-a", produces="")
    drone_b = _make_drone("drone-b", accepts="OpportunityBatch")
    lookup = {"drone-a": drone_a, "drone-b": drone_b}

    chain = ChainDefinition(
        id="no-prod",
        name="No Produces",
        description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="drone-b"),
        ),
        edges=(
            ChainEdge(from_node="n1", to_node="n2"),
        ),
    )

    result = validate(chain, lookup)
    assert result.ok is False
    match = [e for e in result.errors if "no produces type" in e]
    assert len(match) >= 1
    assert "OpportunityBatch" in match[0]


# ── Draft nodes ────────────────────────────────────────────────────


def test_draft_fields_default() -> None:
    """ChainNode defaults is_draft=False, draft fields empty."""
    node = ChainNode(id="n1", drone_id="drone-a")
    assert node.is_draft is False
    assert node.draft_name == ""
    assert node.draft_accepts == ""
    assert node.draft_produces == ""
    assert node.draft_brief == ""


def test_roundtrip_with_draft_node() -> None:
    """Chain with a draft node saves and reloads preserving draft fields."""
    chain = ChainDefinition(
        id="draft-chain", name="Draft Chain", description="Has draft",
        nodes=(
            ChainNode(id="d1", drone_id="drone-a"),
            ChainNode(id="d2", drone_id="__draft__", is_draft=True,
                      draft_name="My Draft", draft_accepts="text",
                      draft_produces="json", draft_brief="Does stuff"),
        ),
        edges=(ChainEdge(from_node="d1", to_node="d2"),),
    )
    data = asdict(chain)
    reconstructed = _chain_from_dict(data)
    assert reconstructed == chain
    draft = [n for n in reconstructed.nodes if n.is_draft][0]
    assert draft.draft_name == "My Draft"
    assert draft.draft_accepts == "text"
    assert draft.draft_produces == "json"
    assert draft.draft_brief == "Does stuff"


def test_validate_fails_for_draft_node() -> None:
    """validate() fails when any node is_draft."""
    drone_a = _make_drone("drone-a")
    lookup = {"drone-a": drone_a}
    chain = ChainDefinition(
        id="draft-run", name="Draft Run", description="",
        nodes=(
            ChainNode(id="n1", drone_id="drone-a"),
            ChainNode(id="n2", drone_id="__draft__", is_draft=True,
                      draft_name="WIP"),
        ),
        edges=(ChainEdge(from_node="n1", to_node="n2"),),
    )
    result = validate(chain, lookup)
    assert result.ok is False
    assert any("draft" in e.lower() for e in result.errors)
    assert any("n2" in e for e in result.errors)
    assert any("save it before running" in e for e in result.errors)


def test_validate_draft_error_message_exact() -> None:
    """Error message for draft node is human-readable."""
    chain = ChainDefinition(
        id="draft-msg", name="Draft Msg", description="",
        nodes=(ChainNode(id="n1", drone_id="__draft__", is_draft=True,
                         draft_name="My Draft"),),
    )
    result = validate(chain, {})
    assert result.ok is False
    match = [e for e in result.errors if "draft" in e.lower()]
    assert len(match) >= 1
    assert "n1" in match[0]
    assert "save it before running" in match[0]


def test_old_chain_loads_without_draft_fields() -> None:
    """A chain JSON without draft fields loads with defaults."""
    data = {
        "id": "old-chain", "name": "Old", "description": "Old chain",
        "nodes": [{"id": "n1", "drone_id": "drone-a", "position": [10, 20]}],
        "edges": [],
    }
    chain = _chain_from_dict(data)
    node = chain.nodes[0]
    assert node.is_draft is False
    assert node.draft_name == ""

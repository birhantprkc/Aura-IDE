"""Tests for aura.projects.store — ProjectStore class."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aura.projects.store import ProjectStore


def test_create_or_update_project_creates_metadata(tmp_path):
    """First call creates .aura/project.json with correct fields."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    project = store.create_or_update_project(ws, name="My Project")
    
    assert project.name == "My Project"
    assert project.root_path == ws
    assert project.id and len(project.id) > 0
    
    metadata_path = ws / ".aura" / "project.json"
    assert metadata_path.exists()
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert data["name"] == "My Project"
    assert data["root_path"] == ws.as_posix()


def test_create_or_update_project_updates_existing(tmp_path):
    """Second call with same root returns existing project + updates name."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    p1 = store.create_or_update_project(ws, name="Original")
    p2 = store.create_or_update_project(ws, name="Updated")
    assert p2.id == p1.id
    assert p2.name == "Updated"
    # Verify on disk
    data = json.loads((ws / ".aura" / "project.json").read_text(encoding="utf-8"))
    assert data["name"] == "Updated"


def test_create_thread_creates_metadata(tmp_path):
    """create_thread writes a thread JSON under .aura/threads/."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    project = store.create_or_update_project(ws, name="Test")
    
    thread = store.create_thread(project, title="My Thread")
    assert thread.title == "My Thread"
    assert thread.project_id == project.id
    
    thread_path = ws / ".aura" / "threads" / f"{thread.id}.json"
    assert thread_path.exists()
    data = json.loads(thread_path.read_text(encoding="utf-8"))
    assert data["title"] == "My Thread"
    assert data["project_id"] == project.id
    assert data["conversation_path"] is None


def test_save_thread_updates_conversation_path(tmp_path):
    """Thread.conversation_path is persisted and roundtrips."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    project = store.create_or_update_project(ws)
    thread = store.create_thread(project, title="Test")
    
    conv_path = ws / ".aura" / "conversations" / "test.json"
    conv_path.parent.mkdir(parents=True, exist_ok=True)
    conv_path.write_text("{}", encoding="utf-8")
    
    thread.conversation_path = conv_path
    store.save_thread(project, thread)
    
    loaded = store.load_thread(project, thread.id)
    assert loaded is not None
    assert loaded.conversation_path == conv_path


def test_list_threads_returns_sorted(tmp_path):
    """list_threads returns threads sorted by updated_at descending."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    project = store.create_or_update_project(ws)
    
    t1 = store.create_thread(project, title="First")
    t2 = store.create_thread(project, title="Second")
    
    threads = store.list_threads(project)
    assert len(threads) == 2
    # Second was created later, so should be first
    assert threads[0].title == "Second"
    assert threads[1].title == "First"


def test_last_thread_id_updated(tmp_path):
    """ProjectSpace.last_thread_id reflects the most recent thread."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    project = store.create_or_update_project(ws)
    assert project.last_thread_id is None
    
    thread = store.create_thread(project, title="New")
    assert project.last_thread_id == thread.id
    
    # Reload and verify
    reloaded = store.load_project(project.id)
    assert reloaded is not None
    assert reloaded.last_thread_id == thread.id


def test_touch_thread_updates_conversation_path(tmp_path):
    """touch_thread updates thread updated_at and conversation_path."""
    ws = tmp_path / "project"
    ws.mkdir()
    store = ProjectStore()
    project = store.create_or_update_project(ws)
    thread = store.create_thread(project, title="Test")
    
    conv_path = ws / ".aura" / "conversations" / "touched.json"
    store.touch_thread(project, thread.id, conversation_path=conv_path)
    
    loaded = store.load_thread(project, thread.id)
    assert loaded is not None
    assert loaded.conversation_path == conv_path

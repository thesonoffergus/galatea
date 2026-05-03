"""Tests for the event log and director stub."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from events.log import (
    EventEntry,
    EventLog,
    EventSeverity,
    EventType,
    NPCRole,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry(
    event_type: EventType = EventType.GENERIC,
    description: str = "Something happened.",
    severity: EventSeverity = EventSeverity.MINOR,
    tags: set[str] | None = None,
    npc_roles: list[NPCRole] | None = None,
    zone_id: str | None = None,
) -> EventEntry:
    return EventEntry(
        event_type=event_type,
        description=description,
        severity=severity,
        tags=tags or set(),
        npc_roles=npc_roles or [],
        zone_id=zone_id,
    )


# ── EventEntry ────────────────────────────────────────────────────────────────

def test_event_entry_has_id_and_timestamp():
    e = _entry()
    assert len(e.id) == 12
    assert e.timestamp.tzinfo is not None


def test_event_entry_actor_ids():
    roles = [NPCRole("npc_a", "actor"), NPCRole("npc_b", "target")]
    e = _entry(npc_roles=roles)
    assert e.actor_ids() == ["npc_a"]
    assert "npc_b" in e.involved_npc_ids()


def test_event_entry_to_dict_keys():
    e = _entry(tags={"combat", "forest"})
    d = e.to_dict()
    assert set(d.keys()) == {
        "id", "event_type", "description", "timestamp",
        "npc_roles", "zone_id", "severity", "tags", "payload", "amplification",
    }
    assert d["tags"] == ["combat", "forest"]  # sorted


# ── EventLog ──────────────────────────────────────────────────────────────────

def test_event_log_record_and_len():
    log = EventLog()
    log.record(_entry(description="A"))
    log.record(_entry(description="B"))
    assert len(log) == 2


def test_event_log_all_oldest_first():
    log = EventLog()
    log.record(_entry(description="first"))
    log.record(_entry(description="second"))
    entries = log.all()
    assert entries[0].description == "first"
    assert entries[1].description == "second"


def test_event_log_recent_newest_first():
    log = EventLog()
    for i in range(5):
        log.record(_entry(description=str(i)))
    recent = log.recent(3)
    assert len(recent) == 3
    assert recent[0].description == "4"
    assert recent[2].description == "2"


def test_event_log_max_entries_ring():
    log = EventLog(max_entries=3)
    for i in range(5):
        log.record(_entry(description=str(i)))
    assert len(log) == 3
    # Oldest two (0, 1) were evicted
    descriptions = [e.description for e in log.all()]
    assert "0" not in descriptions
    assert "4" in descriptions


def test_event_log_emit_returns_entry():
    log = EventLog()
    e = log.emit(EventType.CRAFT_SUCCESS, "A sword was forged.")
    assert isinstance(e, EventEntry)
    assert e.event_type == EventType.CRAFT_SUCCESS
    assert len(log) == 1


def test_event_log_by_type():
    log = EventLog()
    log.emit(EventType.DIALOGUE, "Player spoke.")
    log.emit(EventType.CRAFT_SUCCESS, "Item crafted.")
    log.emit(EventType.DIALOGUE, "NPC spoke.")
    dialogue_entries = log.by_type(EventType.DIALOGUE)
    assert len(dialogue_entries) == 2
    assert all(e.event_type == EventType.DIALOGUE for e in dialogue_entries)


def test_event_log_by_npc():
    log = EventLog()
    log.emit(EventType.GENERIC, "A", npc_roles=[NPCRole("npc_a", "actor")])
    log.emit(EventType.GENERIC, "B", npc_roles=[NPCRole("npc_b", "actor")])
    log.emit(EventType.GENERIC, "C", npc_roles=[NPCRole("npc_a", "witness"), NPCRole("npc_b", "actor")])
    a_entries = log.by_npc("npc_a")
    assert len(a_entries) == 2


def test_event_log_by_zone():
    log = EventLog()
    log.emit(EventType.GENERIC, "In forge", zone_id="forge_room")
    log.emit(EventType.GENERIC, "In tavern", zone_id="common_room")
    forge_entries = log.by_zone("forge_room")
    assert len(forge_entries) == 1
    assert forge_entries[0].zone_id == "forge_room"


def test_event_log_by_tag():
    log = EventLog()
    log.emit(EventType.CRAFT_SUCCESS, "Sword forged", tags={"craft", "weapon"})
    log.emit(EventType.GATHER, "Ore gathered", tags={"craft", "ore"})
    log.emit(EventType.DIALOGUE, "Chatting", tags={"social"})
    craft_entries = log.by_tag("craft")
    assert len(craft_entries) == 2


def test_event_log_by_severity():
    log = EventLog()
    log.emit(EventType.GENERIC, "Trivial", severity=EventSeverity.TRIVIAL)
    log.emit(EventType.GENERIC, "Minor",   severity=EventSeverity.MINOR)
    log.emit(EventType.GENERIC, "Major",   severity=EventSeverity.MAJOR)
    major_up = log.by_severity(EventSeverity.MAJOR)
    assert len(major_up) == 1
    assert major_up[0].severity == EventSeverity.MAJOR


def test_event_log_since():
    log = EventLog()
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    log.record(_entry(description="old"))
    recent = log.since(future)
    assert recent == []
    all_since_past = log.since(past)
    assert len(all_since_past) == 1


def test_event_entry_amplification_default():
    e = _entry()
    assert e.amplification == 1.0


def test_event_entry_amplification_settable():
    log = EventLog()
    e = log.emit(EventType.GENERIC, "Amplified", amplification=3.0)
    assert e.amplification == 3.0


# ── Director stub ─────────────────────────────────────────────────────────────

def test_director_tick_runs_without_error():
    from director.director import Director
    log = EventLog()
    log.emit(EventType.DIALOGUE, "A turn.")
    d = Director()
    d.tick(log)  # must not raise


def test_director_tick_does_not_modify_log():
    from director.director import Director
    log = EventLog()
    log.emit(EventType.GENERIC, "Event.")
    before = len(log)
    Director().tick(log)
    assert len(log) == before

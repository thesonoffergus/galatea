"""
Stub director module.

The director is a listener over the event log. At MVP it is wired into
the tick cadence but applies no amplification — turning it on is a code
change in `tick()` below, not a plumbing project.

Design notes (parked, do not implement yet):
  - Scorer: heuristic-only vs. LLM-assisted for ambiguous cases.
  - Pacing: director modulates aggressiveness based on current narrative density.
  - Casting agent: identifies NPCs suited to play roles in emerging arcs.
"""
from __future__ import annotations

from events.log import EventEntry, EventLog


class Director:
    """
    Stub director. Receives events; currently applies no amplification.

    Interface is stable — real scoring logic slots in without changes
    to callers.
    """

    def tick(self, log: EventLog) -> None:
        """
        Called once per simulation tick after all events for that tick
        have been recorded.

        Stub: scans recent events, applies no amplification.
        """
        _recent = log.recent(100)  # noqa: F841 — will be consumed by scorer
        # TODO: score events and call amplification primitives


# Module-level singleton
director = Director()

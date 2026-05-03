"""
Tier promotion and demotion logic.

Tier governs simulation depth. Promotion is cheap (no data loss).
Demotion triggers LLM-based history compression: the NPC's episodic
memories are condensed into a `narrative_summary` paragraph that is
injected into prompts if the NPC is ever re-promoted.

Reach score — a single float that summarises how much simulation
investment an NPC deserves — is computed from:
  - relationship count and average affinity magnitude
  - number of active goals
  - memory salience sum
  - explicit director boost (reach_score override)

The director can always force a tier change directly; these helpers
are the default automatic path.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import settings
from knowledge.memory import IndividualMemory
from knowledge.store import MemoryStore
from llm.runner import LLMRunner
from llm.types import LLMOptions, Message
from npc.schema import NPC, NPCTier


# ── Thresholds (driven by config) ────────────────────────────────────────────

PROMOTE_THRESHOLD: dict[int, float] = {
    # score needed to move FROM tier n TO tier n+1
    0: settings.tier.promote_t0,
    1: settings.tier.promote_t1,
    2: settings.tier.promote_t2,
}

DEMOTE_THRESHOLD: dict[int, float] = {
    # score below which demotion FROM tier n TO tier n-1 triggers
    1: settings.tier.demote_t1,
    2: settings.tier.demote_t2,
    3: settings.tier.demote_t3,
}


# ── Reach score ───────────────────────────────────────────────────────────────

def compute_reach_score(npc: NPC, memory: IndividualMemory) -> float:
    """
    Heuristic importance score for an NPC.

    Higher = more simulation investment warranted.
    """
    rel_score = len(npc.relationships) * 0.5
    if npc.relationships:
        avg_affinity_mag = sum(
            abs(r.affinity) for r in npc.relationships.values()
        ) / len(npc.relationships)
        rel_score += avg_affinity_mag * 2.0

    goal_score = len(npc.active_goals()) * 1.5

    salience_sum = sum(e.salience for e in memory.all_entries())
    mem_score = min(salience_sum * 0.3, 5.0)  # cap memory contribution

    return rel_score + goal_score + mem_score


# ── Promotion ─────────────────────────────────────────────────────────────────

@dataclass
class TierChangeResult:
    npc_id: str
    old_tier: NPCTier
    new_tier: NPCTier
    narrative_summary: str = ""  # non-empty only on demotion with compression


def promote(npc: NPC, store: MemoryStore) -> TierChangeResult | None:
    """
    Promote by one tier if reach_score meets the threshold.
    Returns None if already at max tier or score is insufficient.
    """
    if npc.tier >= NPCTier.T3:
        return None
    memory = store.get(npc.id)
    score = compute_reach_score(npc, memory)
    npc.reach_score = score

    threshold = PROMOTE_THRESHOLD.get(npc.tier)
    if threshold is None or score < threshold:
        return None

    old_tier = npc.tier
    npc.tier = NPCTier(npc.tier + 1)

    # Re-register at new tier capacity (preserves existing entries, trims if needed)
    old_mem = memory.all_entries()
    new_mem = store.register_npc(npc.id, npc.tier)
    for entry in old_mem:
        new_mem.add(entry)

    return TierChangeResult(npc_id=npc.id, old_tier=old_tier, new_tier=npc.tier)


def demote(
    npc: NPC,
    store: MemoryStore,
    runner: LLMRunner | None = None,
) -> TierChangeResult | None:
    """
    Demote by one tier if reach_score falls below the demotion threshold.
    If a runner is provided, the NPC's episodic memory is compressed into
    a narrative_summary before the memory store is trimmed to the new
    tier capacity.
    Returns None if already at T0 or score is still above threshold.
    """
    if npc.tier <= NPCTier.T0:
        return None
    memory = store.get(npc.id)
    score = compute_reach_score(npc, memory)
    npc.reach_score = score

    threshold = DEMOTE_THRESHOLD.get(npc.tier)
    if threshold is None or score >= threshold:
        return None

    summary = ""
    if runner is not None:
        summary = _compress_history(npc, memory, runner)
        npc.narrative_summary = summary

    old_tier = npc.tier
    npc.tier = NPCTier(npc.tier - 1)

    # Re-register at new (lower) capacity; salience-based eviction keeps best entries
    old_mem = memory.all_entries()
    new_mem = store.register_npc(npc.id, npc.tier)
    for entry in old_mem:
        new_mem.add(entry)

    return TierChangeResult(
        npc_id=npc.id,
        old_tier=old_tier,
        new_tier=npc.tier,
        narrative_summary=summary,
    )


def force_tier(
    npc: NPC,
    store: MemoryStore,
    new_tier: NPCTier,
    runner: LLMRunner | None = None,
) -> TierChangeResult:
    """
    Director override: set tier directly regardless of reach score.
    Compresses history if demoting and runner is provided.
    """
    old_tier = npc.tier
    summary = ""

    if new_tier < old_tier and runner is not None:
        memory = store.get(npc.id)
        summary = _compress_history(npc, memory, runner)
        npc.narrative_summary = summary

    npc.tier = new_tier
    old_mem = store.get(npc.id).all_entries()
    new_mem = store.register_npc(npc.id, npc.tier)
    for entry in old_mem:
        new_mem.add(entry)

    return TierChangeResult(
        npc_id=npc.id,
        old_tier=old_tier,
        new_tier=new_tier,
        narrative_summary=summary,
    )


# ── History compression ───────────────────────────────────────────────────────

_COMPRESSION_SYSTEM = (
    "You are a narrator compressing an NPC's episodic memories into a brief "
    "narrative summary for a medieval life simulation. Write 2–4 sentences in "
    "third person, past tense, focusing on relationships, significant events, "
    "and lasting impressions. Omit trivial details. Be concrete and specific."
)


def _compress_history(npc: NPC, memory: IndividualMemory, runner: LLMRunner) -> str:
    entries = memory.all_entries()
    if not entries:
        return ""

    bullet_list = "\n".join(f"- {e.content}" for e in entries)
    user_msg = (
        f"NPC: {npc.name} ({npc.role})\n\n"
        f"Memories to compress:\n{bullet_list}\n\n"
        "Write the narrative summary now."
    )
    messages = [
        Message(role="system", content=_COMPRESSION_SYSTEM),
        Message(role="user", content=user_msg),
    ]
    try:
        response = runner.logged_chat(
            messages,
            options=LLMOptions(temperature=0.4, max_tokens=200),
            tags={f"npc:{npc.id}", "type:compression"},
        )
        return response.content.strip()
    except Exception:
        # Compression failure is non-fatal — return a plain fallback
        recent = entries[-3:]
        return "; ".join(e.content for e in recent)

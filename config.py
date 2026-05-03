"""
Tunable constants — all values here are defaults intended to be overridden
per game implementation. Do not hard-code these values elsewhere.
"""

from pydantic import BaseModel


class TimeConfig(BaseModel):
    real_seconds_per_game_day: float = 900.0  # 15 minutes
    ticks_per_game_hour: int = 1
    game_hours_per_day: int = 24

    @property
    def real_seconds_per_tick(self) -> float:
        return self.real_seconds_per_game_day / (self.game_hours_per_day * self.ticks_per_game_hour)


class TierConfig(BaseModel):
    # Promotion score thresholds — score needed to move FROM tier n TO n+1
    promote_t0: float = 2.0
    promote_t1: float = 5.0
    promote_t2: float = 12.0

    # Demotion score thresholds — score below which demotion FROM tier n triggers
    demote_t1: float = 1.0
    demote_t2: float = 3.0
    demote_t3: float = 8.0

    # Decay rates — reach score lost per tick without reinforcing contact
    decay_per_tick_t1: float = 0.05
    decay_per_tick_t2: float = 0.10
    decay_per_tick_t3: float = 0.15


class CraftingConfig(BaseModel):
    # Default quality weighting (must sum to 1.0)
    quality_weight_material: float = 0.40
    quality_weight_tool: float = 0.15
    quality_weight_character_skill: float = 0.40
    quality_weight_environment: float = 0.05

    # Skill decay (disabled by default)
    skill_decay_enabled: bool = False
    skill_decay_rate_per_day: float = 0.001


class SimConfig(BaseModel):
    # Tick cadences by tier (in game-hours between ticks)
    tick_interval_t0: int = 24
    tick_interval_t1: int = 4
    tick_interval_t2: int = 1
    tick_interval_t3: int = 1

    # Off-screen NPC crafting: below this tier, use stochastic restocking
    full_crafting_chain_min_tier: int = 2

    # Per-tick probabilities
    t1_action_probability: float = 0.25   # chance a T1 NPC acts each tick
    gossip_probability: float = 0.10      # chance a memory propagates to community KB
    rel_drift_magnitude: float = 0.02     # max relationship affinity drift per tick


class LLMConfig(BaseModel):
    default_runner: str = "ollama"
    default_model: str = "llama3.2"
    dialogue_max_tokens: int = 120
    summary_max_tokens: int = 400
    menu_options_count: int = 3
    temperature: float = 0.8


class Config(BaseModel):
    time: TimeConfig = TimeConfig()
    tier: TierConfig = TierConfig()
    crafting: CraftingConfig = CraftingConfig()
    sim: SimConfig = SimConfig()
    llm: LLMConfig = LLMConfig()

    # Affordance graph search radius for "nearby" preconditions (graph hops)
    nearby_radius_hops: int = 1


# Module-level singleton — import and use directly
settings = Config()

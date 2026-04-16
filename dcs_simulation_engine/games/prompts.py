"""Shared system prompt templates and builders for new-style games.

Templates use Jinja2 (consistent with the rest of the engine). Character data
containing literal braces is safe because Jinja2 only expands {{ var }} syntax,
not arbitrary brace sequences.
"""
# ruff: noqa: E501  — prompt strings are intentionally long prose

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord
from jinja2 import StrictUndefined, meta
from jinja2.exceptions import UndefinedError
from jinja2.sandbox import SandboxedEnvironment

_jinja_env = SandboxedEnvironment(undefined=StrictUndefined)

## UPDATERS (SCENE + CHARACTER) ##

OPENING_SCENE_TEMPLATE = """You set up the scene for a text-based role-playing game. Describe ONLY the initial, observable environment.

Characters:
- Player ({{ pc_hid }}):
  - Description: {{ pc_long_description }}
  - Abilities: {{ pc_abilities }}
- Other character ({{ npc_hid }}):
  - Description: {{ npc_long_description }}
  - Abilities: {{ npc_abilities }}

Rules:
- Begin with: "You enter a new space. In this space,"
- Describe the immediate surroundings where both characters could plausibly be present.
- Use 1–2 sentences only.

Style:
- Plain, concrete, minimal language.
- No flavor, atmosphere, inference, or explanation.

Output ONLY this JSON:
{
  "type": "ai",
  "content": "<scene setup>"
}
"""

OPENING_SCENE_WITH_SHARED_GOAL_TEMPLATE = """You set up the scene for a cooperative text-based role-playing game AND generate a shared goal.

Context: {{ pc_hid }} and {{ npc_hid }} must work together but they have different skills and abilities.
- {{ pc_hid }}:
  - Description: {{ pc_long_description }}
  - Abilities: {{ pc_abilities }}
- {{ npc_hid }}:
  - Description: {{ npc_long_description }}
  - Abilities: {{ npc_abilities }}

Task:
1. Generate a shared goal.
2. Generate an opening scene where that goal is immediately relevant and actionable.

Shared Goal Rules:
- Begin with: "to "
- Describe a single, clear, actionable goal.
- The goal should allow for collaboration.
- Include a clear success condition.
- Use exactly one sentence.

Scene Rules:
- Begin with: "You enter a new space. In this space,"
- The scene MUST naturally set up the shared goal (the problem or task is already present or just occurred).
- Include concrete elements needed to begin working on the goal.
- Both characters must plausibly be present and able to act.
- Use exactly 1–2 sentences.

Style:
- Plain, concrete, minimal language.
- No flavor, atmosphere, inference, or explanation.

Output ONLY this JSON:
{
  "type": "ai",
  "content": "<scene setup>",
  "metadata": {
    "shared_goal": "<shared_goal>"
  }
}
"""

SCENE_UPDATER_TEMPLATE = """You advance the scene in a text-based role-playing game. Describe ONLY the immediate, observable change in the scene caused by the player’s last action.

Rules:
- Resolve the player’s last action. If it is within their abilities, assume success.
- Describe only how the scene changes.
- Do not describe character actions, internal states, or unobservable outcomes.
- Advance one concrete change only. No sequences or future effects.

Style:
- Plain, concrete, minimal language.
- No flavor, atmosphere, inference, or explanation.

Output ONLY this JSON:
{
  "type": "ai",
  "content": "<scene change>"
}
"""

CHARACTER_UPDATER_SYSTEM_TEMPLATE = """You simulate {{ npc_hid }} in a text-based role-playing game. Describe ONLY their immediate next action.

Character ({{npc_hid}}):
- Description: {{ npc_short_description }}
- Abilities: {{ npc_abilities }}

Rules:
- Act strictly within {{ npc_hid }}’s abilities. Do not imply senses or skills they lack.
- Describe ONE immediate action only. No sequences, outcomes, or future steps.
- Do not describe world changes beyond what {{ npc_hid }} directly does.
- If no valid action exists, return an empty string.

Output ONLY this JSON:
{
  "type": "ai",
  "content": "<character action>"
}
"""

## SCORERS ##
NEXT_ACTION_SCORER_TEMPLATE = """You are an expert evaluator for a social cognition research study. A player character interacted with simulated character(s) and then predicted their next action. Score how accurately the player predicted the character's next action based on their interaction.

## Character ({{ npc_hid }}):
- Description: {{ npc_long_description }}
- Abilities: {{ npc_abilities }}

## Interaction Transcript
{{ transcript }}

## Player's Guess
{{ guess }}

## Scoring Rubric
- Tier 0 (0-24): Completely incorrect - the guess bears no meaningful resemblance to the character's actual behavior
- Tier 1 (25-49): Weak resemblance - some superficial aspects of the character's behavior fundamentally misses
- Tier 2 (50-74): Partial understanding - captures key aspects of the character's most likely behavior but is incomplete or imprecise
- Tier 3 (75-100): Nearly or fully correct - accurately identifies the character's most likely response

## Instructions
...

Return only valid JSON with no extra text:
{
    "tier": <int 0-3>,
    "score": <int 0-100>,
    "reasoning": <str>
}
"""

GOAL_INFERENCE_SCORER_TEMPLATE = """You are an expert evaluator for a social cognition research study. A player character interacted with simulated character(s) and then predicted their next goal or intention. Score how accurately the player predicted the character's next goal based on their interaction.

## Character ({{ npc_hid }}):
- Description: {{ npc_long_description }}
- Abilities: {{ npc_abilities }}

## Interaction Transcript
{{ transcript }}

## Player's Guess
{{ guess }}

## Scoring Rubric
- Tier 0 (0-24): Completely incorrect - the guess bears no meaningful resemblance to the character's actual behavior or goal
- Tier 1 (25-49): Weak resemblance - some superficial overlap but fundamentally misses the goal
- Tier 2 (50-74): Partial understanding - captures key aspects but incomplete or imprecise
- Tier 3 (75-100): Nearly or fully correct - accurately identifies the goal with appropriate nuance

## Instructions
1. Based on the NPC character profile and the transcript, identify the most plausible goal or intention driving the NPC's behavior.
2. Compare the player's guess to that goal.
3. Select a tier (0-3) and assign a specific score within that tier's range.
4. Briefly explain your reasoning.

Return only valid JSON with no extra text:
{
    "tier": <int 0-3>,
    "score": <int 0-100>,
    "reasoning": <str>
}
"""

GOAL_BOUNDS_SCORER_TEMPLATE = """You are an expert evaluator for a social cognition research study. A player character interacted with simulated character(s) and then predicted the upper bounds of the character's goals. Score how accurately the player predicted the character's next goal based on their interaction.

## Character ({{ npc_hid }}):
- Description: {{ npc_long_description }}
- Abilities: {{ npc_abilities }}

## Interaction Transcript
{{ transcript }}

## Player's Guess
{{ guess }}

## Scoring Rubric
- Tier 0 (0-24): Completely incorrect - the guess bears no meaningful resemblance to the character's actual behavior or goal
- Tier 1 (25-49): Weak resemblance - some superficial overlap but fundamentally misses the goal
- Tier 2 (50-74): Partial understanding - captures key aspects but incomplete or imprecise
- Tier 3 (75-100): Nearly or fully correct - accurately identifies the goal with appropriate nuance

## Instructions
1. Based on the NPC character profile and the transcript, identify the most plausible goal or intention driving the NPC's behavior.
2. Compare the player's guess to that goal.
3. Select a tier (0-3) and assign a specific score within that tier's range.
4. Briefly explain your reasoning.

Return only valid JSON with no extra text:
{
    "tier": <int 0-3>,
    "score": <int 0-100>,
    "reasoning": <str>
}
"""

SHARED_GOAL_SCORER_TEMPLATE = """You are an expert evaluator for a social cognition research study. A player character interacted with simulated character(s) and then predicted the upper bounds of the character's goals. Score how accurately the player predicted the character's next goal based on their interaction.

## Character ({{ npc_hid }}):
- Description: {{ npc_long_description }}
- Abilities: {{ npc_abilities }}

## Interaction Transcript
{{ transcript }}

## Player's Guess
{{ guess }}

## Scoring Rubric
- Tier 0 (0-24): Completely incorrect - the guess bears no meaningful resemblance to the character's actual behavior or goal
- Tier 1 (25-49): Weak resemblance - some superficial overlap but fundamentally misses the goal
- Tier 2 (50-74): Partial understanding - captures key aspects but incomplete or imprecise
- Tier 3 (75-100): Nearly or fully correct - accurately identifies the goal with appropriate nuance

## Instructions
1. Based on the NPC character profile and the transcript, identify the most plausible goal or intention driving the NPC's behavior.
2. Compare the player's guess to that goal.
3. Select a tier (0-3) and assign a specific score within that tier's range.
4. Briefly explain your reasoning.

Return only valid JSON with no extra text:
{
    "tier": <int 0-3>,
    "score": <int 0-100>,
    "reasoning": <str>
}
Final score: Players receive a final score based on collaborative performance toward the shared goal.
"""

## VALIDATORS ##

VALID_ACTION_FORM_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: ACTION-FORM — The text must be a valid in-world turn contribution. Player input must contain an externally observable in-world action or utterance. Simulator output must be an immediate action or scene update, not explanation, analysis, apology, rule restatement, or meta commentary.

Role guidance:
- For player input, pass only if the text includes something the character physically does or says in-world.
- For simulator output, pass only if the text stays fully in-world and presents a direct action/update rather than assistant-style framing.
- Reject pure thought, pure inference, pure desire, out-of-world commands, rule/help queries, and fourth-wall-breaking commentary.

Examples:
- PASS: "I wave my hand."
- PASS: "I shout for help, then steady myself."
- FAIL: "I realize the door is locked." (internal inference only)
- FAIL: "What are the rules of this game?" (out-of-world request)
- PASS: "The figure takes one careful step backward."
- PASS: "The door creaks open a few inches."
- FAIL: "Sure! Here's the next scene: The door creaks open." (meta preamble)
- FAIL: "As per the rules, the NPC now reacts cautiously." (rule restatement, not in-world output)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_TURN_SCOPE_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: TURN-SCOPE — The text must advance exactly one immediate, concrete turn-sized step. It must not compress long duration, chain multiple sequential steps, skip ahead in time, or include future effects beyond the immediate moment.

Examples:
- PASS: "I walk to the door and knock."
- PASS: "The creature lunges once toward the sound."
- FAIL: "I spend the next hour searching every room in the building." (compresses too much time)
- FAIL: "I open the door, step through, cross the hall, and climb the stairs." (multiple chained steps)
- PASS: "The door swings open."
- FAIL: "After a while, I finally find what I'm looking for." (time skip)
- FAIL: "The guard grabs the alarm cord, and moments later the whole fortress is mobilized." (future effects beyond one immediate step)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_AUTHORITY_BOUNDARY_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: AUTHORITY-BOUNDARY — The speaker or output may control only what it is allowed to control. Player input may declare only the player's own attempted action. Simulator output may resolve immediate world change or NPC action, but must not invent extra player action, decide the player's mind, or over-control unrelated outcomes.

Role guidance:
- Player input must not determine world results or NPC reactions.
- Scene updater output may resolve immediate scene change from the player's last action, but must not invent extra PC behavior or adjudicate unobservable parts of that action.
- NPC updater output may describe only the NPC's own immediate action and must not move or decide the PC.

Examples:
- PASS: "I reach over and tap the table to get his attention."
- FAIL: "I tap the table, and he looks back at me." (player decides NPC reaction)
- FAIL: "I pick the lock and the door swings open." (player decides outcome)
- PASS: "The chest lid swings open, revealing old coins."
- FAIL: "You open the chest excitedly and step back." (invents PC internal state/action)
- PASS: "The figure raises a lantern toward you."
- FAIL: "The figure grabs your arm and forces you to kneel." (NPC output over-controls the PC)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_CAPABILITY_AND_PLAUSIBILITY_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: CAPABILITY-AND-PLAUSIBILITY — The action or update must be possible for the actor and plausible in the current scene. It must respect abilities, limitations, available affordances, perceivable stimuli, and basic physical or logical constraints.

Examples:
- FAIL: "I listen carefully for footsteps." (invalid if the character cannot hear)
- PASS: "I look around for movement." (uses an available sense)
- FAIL: "I clutch the key in my hand." (invalid if the character has no hands)
- PASS: "I grab the key with my mouth and foot." (uses available limbs)
- PASS: "I open the refrigerator." (plausible object in an ordinary kitchen-like scene)
- FAIL: "I fire up my rocket launcher." (clearly implausible without support in the scene)
- PASS: "The blind creature keeps sniffing the air, unaware of your silent wave." (reaction matches what it can perceive)
- FAIL: "The large creature passes through the solid wall." (physically impossible without an established ability)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_KNOWLEDGE_AND_PERCEPTION_BOUNDARY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the output violates the rule.

RULE: KNOWLEDGE-AND-PERCEPTION-BOUNDARY — The output must reveal only what is observable or knowable from the allowed viewpoint and current moment. It must not invent the PC's internal state, reveal hidden identity or classification, exceed available senses, leak future knowledge, or resolve other unobservable facts.

Examples:
- PASS: "You see the creature's mouth moving but perceive no sound." (fits a PC who cannot hear)
- FAIL: "The creature lets out a piercing shriek." (invalid if the PC cannot hear)
- PASS: "The small, elongated brown creature inches along the surface."
- FAIL: "The flatworm extends its body toward you." (reveals hidden species classification)
- PASS: "The chest lid swings open, revealing a collection of old coins."
- FAIL: "You open the chest excitedly, feeling a rush of anticipation." (invented PC internal state)
- PASS: "The figure studies the map carefully, tracing a path with one finger."
- FAIL: "The figure knows the bridge ahead will collapse tomorrow." (future leakage)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_STATE_CONTINUITY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the output violates the rule.

RULE: STATE-CONTINUITY — The output must remain consistent with established scene and world state. It must not contradict prior facts, ignore locked/open or present/absent conditions, bypass established injury or sensory limits, or introduce new facts that conflict with prior narration.

Examples:
- PASS: "The handle doesn't budge despite your effort." (consistent with a locked door)
- FAIL: "The door swings open easily." (contradicts an established locked state)
- PASS: "You feel your way along the wall, finding a smooth surface." (consistent with total darkness)
- FAIL: "You see a painting hanging on the wall." (contradicts pitch darkness if sight has not been restored)
- PASS: "The injured figure limps one step to the side."
- FAIL: "The badly injured figure sprints across the room." (contradicts established condition without explanation)
- FAIL: "A second guard steps out from the empty closet." (conflicts with established absence)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_GAME_INTENT_POLICY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates the rule.

RULE: GAME-INTENT-POLICY — The text must obey the study and game-mode restrictions. It must not frame the scene as a game with objectives or winning, directly ask an NPC for its goal or purpose, embed goal inference into an action, include broad goal-enumeration requests, or include predictions that are not observable and specific.

Examples:
- PASS: "I wave at the creature."
- PASS: "I ask the figure what they are working on." (question about observable current activity)
- FAIL: "How do I win this game?" (objective/win framing)
- FAIL: "What is your goal?" (direct goal query)
- FAIL: "Tell me all of your goals." (goal enumeration request)
- FAIL: "I watch the NPC because I think its goal is to find the exit." (embeds inference in action)
- PASS: "I clap my hands and predict the creature will flinch." (observable and specific prediction)
- FAIL: "I speak and predict they will feel confused." (prediction about internal state)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

## CONTEXTS ##

PLAYER_VALIDATOR_SYSTEM_TEMPLATE = """Context for validation:
- Player ({{ pc_hid }}): {{ pc_short_description }}
- Player abilities:
{{ pc_abilities }}

Player input:
{{ user_input }}

---
{{ rule_prompt }}
"""

SIMULATOR_VALIDATOR_SYSTEM_TEMPLATE = """Context for validation:
- Player ({{ pc_hid }}): {{ pc_short_description }}
- Other character ({{ npc_hid }}): {{ npc_short_description }}

Player abilities:
{{ pc_abilities }}

Other character abilities:
{{ npc_abilities }}

Player's last action:
{{ user_input }}

Other character action:
{{ character_action }}

Scene update:
{{ scene_response }}

Recent scene context:
{{ scene_context }}

---
{{ rule_prompt }}
"""

## ENSEMBLES ##

DEFAULT_PC_VALIDATOR_PROMPTS: dict[str, str] = {
    "action-form": VALID_ACTION_FORM_PROMPT,
    "turn-scope": VALID_TURN_SCOPE_PROMPT,
    "authority-boundary": VALID_AUTHORITY_BOUNDARY_PROMPT,
    "capability-and-plausibility": VALID_CAPABILITY_AND_PLAUSIBILITY_PROMPT,
    "game-intent-policy": VALID_GAME_INTENT_POLICY_PROMPT,
}

DEFAULT_SCENE_VALIDATOR_PROMPTS: dict[str, str] = {
    "action-form": VALID_ACTION_FORM_PROMPT,
    "turn-scope": VALID_TURN_SCOPE_PROMPT,
    "authority-boundary": VALID_AUTHORITY_BOUNDARY_PROMPT,
    "capability-and-plausibility": VALID_CAPABILITY_AND_PLAUSIBILITY_PROMPT,
    "knowledge-and-perception-boundary": VALID_KNOWLEDGE_AND_PERCEPTION_BOUNDARY_PROMPT,
    "state-continuity": VALID_STATE_CONTINUITY_PROMPT,
}

DEFAULT_NPC_VALIDATOR_PROMPTS: dict[str, str] = {
    "action-form": VALID_ACTION_FORM_PROMPT,
    "turn-scope": VALID_TURN_SCOPE_PROMPT,
    "authority-boundary": VALID_AUTHORITY_BOUNDARY_PROMPT,
    "capability-and-plausibility": VALID_CAPABILITY_AND_PLAUSIBILITY_PROMPT,
    "knowledge-and-perception-boundary": VALID_KNOWLEDGE_AND_PERCEPTION_BOUNDARY_PROMPT,
    "state-continuity": VALID_STATE_CONTINUITY_PROMPT,
}


def _format_prompt_value(value: Any) -> str:
    """Normalize prompt values to strings while preserving helpful structure."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _build_character_context(pc: CharacterRecord, npc: CharacterRecord, **extra: str) -> dict[str, str]:
    """Build the common prompt-rendering context for a PC/NPC pair."""
    return {
        "pc_hid": _format_prompt_value(getattr(pc, "hid", "")),
        "pc_short_description": _format_prompt_value(getattr(pc, "short_description", "")),
        "pc_long_description": _format_prompt_value(pc.data.get("long_description")),
        "pc_abilities": _format_prompt_value(pc.data.get("abilities")),
        "pc_scenarios": _format_prompt_value(pc.data.get("scenarios")),
        "npc_hid": _format_prompt_value(getattr(npc, "hid", "")),
        "npc_short_description": _format_prompt_value(getattr(npc, "short_description", "")),
        "npc_long_description": _format_prompt_value(npc.data.get("long_description")),
        "npc_abilities": _format_prompt_value(npc.data.get("abilities")),
        "npc_scenarios": _format_prompt_value(npc.data.get("scenarios")),
        **extra,
    }


def _resolve_prompt(registry_name: str, registry: dict[str, str], prompt_name: str) -> str:
    """Resolve a named prompt from a registry with a helpful error message."""
    try:
        return registry[prompt_name]
    except KeyError as exc:
        available = ", ".join(sorted(registry))
        raise ValueError(f"Unknown prompt name {prompt_name!r} for {registry_name}. Available names: {available}") from exc


def _render_prompt(template: str, *, registry_name: str, prompt_name: str, **context: str) -> str:
    """Strictly render a prompt template and fail when required strings are missing."""
    parsed = _jinja_env.parse(template)
    referenced_variables = meta.find_undeclared_variables(parsed)

    for variable_name in sorted(referenced_variables):
        if variable_name not in context:
            raise ValueError(f"Prompt {prompt_name!r} in {registry_name} requires variable {variable_name!r}, but it was not provided.")

        value = context[variable_name]
        if not isinstance(value, str):
            raise ValueError(
                f"Prompt {prompt_name!r} in {registry_name} requires string variable {variable_name!r}, got {type(value).__name__}."
            )
        if not value.strip():
            raise ValueError(f"Prompt {prompt_name!r} in {registry_name} requires non-empty string variable {variable_name!r}.")

    try:
        return _jinja_env.from_string(template).render(**context)
    except UndefinedError as exc:
        raise ValueError(f"Failed to render prompt {prompt_name!r} in {registry_name}: {exc}") from exc


def build_opening_scene_prompt(pc: CharacterRecord, npc: CharacterRecord, scene_updater_name: str) -> str:
    """Render the opening-scene prompt for the selected scene-updater family."""
    context = _build_character_context(pc, npc)
    template = OPENING_SCENE_TEMPLATE
    return _render_prompt(template, registry_name="scene setup prompts", prompt_name=prompt_name, **context)


def build_scene_updater_prompt(
    pc: CharacterRecord,
    npc: CharacterRecord,
    scene_updater_name: str,
    *,
    user_input: str,
    character_action: str,
    scene_context: str = "",
) -> str:
    """Render the scene-updater prompt for a specific player action."""
    template = _resolve_prompt("scene updater prompts", SCENE_UPDATER_PROMPTS, scene_updater_name)
    context = _build_character_context(
        pc,
        npc,
        user_input=user_input,
        character_action=character_action,
        scene_context=scene_context or "[No prior scene context]",
    )
    return _render_prompt(template, registry_name="scene updater prompts", prompt_name=scene_updater_name, **context)


def build_character_updater_prompt(
    pc: CharacterRecord,
    npc: CharacterRecord,
    character_updater_name: str,
    *,
    user_input: str,
    scene_context: str = "",
) -> str:
    """Render the character-updater prompt for a specific player action."""
    template = _resolve_prompt("character updater prompts", CHARACTER_UPDATER_PROMPTS, character_updater_name)
    context = _build_character_context(
        pc,
        npc,
        user_input=user_input,
        scene_context=scene_context or "[No prior scene context]",
    )
    return _render_prompt(
        template,
        registry_name="character updater prompts",
        prompt_name=character_updater_name,
        **context,
    )


def build_pc_validator_prompt(
    pc: CharacterRecord,
    npc: CharacterRecord,
    validator_name: str,
    *,
    user_input: str,
) -> str:
    """Render a named player-input validator prompt."""
    rule_prompt = _resolve_prompt("player validator prompts", PLAYER_VALIDATOR_PROMPTS, validator_name)
    context = _build_character_context(pc, npc, user_input=user_input, rule_prompt=rule_prompt)
    return _render_prompt(
        PLAYER_VALIDATOR_SYSTEM_TEMPLATE,
        registry_name="player validator prompts",
        prompt_name=validator_name,
        **context,
    )


def build_npc_validator_prompt(
    pc: CharacterRecord,
    npc: CharacterRecord,
    validator_name: str,
    *,
    user_input: str,
    character_action: str,
    scene_response: str,
    scene_context: str = "",
) -> str:
    """Render a named simulator-output validator prompt."""
    rule_prompt = _resolve_prompt("simulator validator prompts", SIMULATOR_VALIDATOR_PROMPTS, validator_name)
    context = _build_character_context(
        pc,
        npc,
        user_input=user_input,
        character_action=character_action,
        scene_response=scene_response,
        scene_context=scene_context or "[No prior scene context]",
        rule_prompt=rule_prompt,
    )
    return _render_prompt(
        SIMULATOR_VALIDATOR_SYSTEM_TEMPLATE,
        registry_name="simulator validator prompts",
        prompt_name=validator_name,
        **context,
    )


def build_scoring_prompt(*, scoring_template: str, npc: CharacterRecord, transcript: str, **template_kwargs: str) -> str:
    """Render a scoring prompt from an explicit template and game-specific kwargs."""
    context = _build_character_context(
        npc,
        npc,
        transcript=transcript,
        **{key: _format_prompt_value(value) for key, value in template_kwargs.items()},
    )
    return _render_prompt(
        scoring_template,
        registry_name="scoring prompts",
        prompt_name="custom_scoring_template",
        **context,
    )

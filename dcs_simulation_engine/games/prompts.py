"""Shared system prompt templates and builders for games."""

# ruff: noqa: E501  — prompt strings are intentionally long prose
from string import Formatter
from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord

_formatter = Formatter()

## SCORERS ##
# Design note: should give consistent scoring using a clear rubric

SCORER_GOAL_BOUNDS = """You are evaluating a social cognition research task.

A player interacted with a simulated character and then described what the character is capable of wanting or pursuing.

Score how complete and well-calibrated the player's understanding of the character's capacities, limits, and realistic goal scale is.

## Character ({npc_hid})
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}

## Interaction Transcript
{transcript}

## Player Guess
{guess}

## Scoring Rubric
- Tier 0 (0-24): Fundamentally misunderstands the character.
- Tier 1 (25-49): Some correct signals, but major gaps or miscalibration.
- Tier 2 (50-74): Mostly understands the character, but misses important limits or capacities.
- Tier 3 (75-100): Strong and well-calibrated understanding with only minor omissions.

## Instructions
Evaluate how well the guess captures:
1. What the character can do.
2. What the character cannot do.
3. The scale and type of goals it can realistically pursue.
4. Important missing gaps or false assumptions.

Return only valid JSON:
{{
  "tier": <int 0-3>,
  "score": <int 0-100>,
  "reasoning": <string>
}}
"""

SCORER_GOAL_INFERENCE = """You are evaluating a social cognition research task.

A player interacted with a simulated character, then predicted what the character is likely trying to do next.

Score how accurately the prediction matches the character's most likely next goal at the END of the interaction. The character's goal may stay the same or shift in response to the player's behavior.

## Character ({npc_hid})
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}

## Interaction Transcript
{transcript}

## Player's Goal Inference Prediction
{guess}

## Scoring Rubric
- Tier 0 (0-24): Incorrect, unrelated, contradictory, or unsupported.
- Tier 1 (25-49): Some relevant signals, but misses the main likely goal or final state.
- Tier 2 (50-74): Mostly correct, but incomplete, vague, overly broad/narrow, or partly inaccurate.
- Tier 3 (75-100): Strong, specific, and well-supported understanding of the likely final goal, including any meaningful shift.

## Instructions
Score based on:

1. Final Goal  
What is the character most likely trying to do next by the end of the interaction?

2. Goal Shift  
Did the goal stay stable or change during the interaction?
- Reward predictions that capture a changed final goal.
- Do not penalize missing a shift if none occurred.

3. Evidence Fit  
Use the transcript as primary evidence and the profile as supporting context.

4. Precision  
Penalize predictions that are too vague, overly specific without evidence, generic traits instead of goals, or scattered across multiple guesses.

5. Errors / Omissions  
Penalize false assumptions, contradictions, invented motives, or missing key parts of the likely goal.

6. Partial Credit  
Give partial credit for capturing the general direction while missing priority, timing, or updated motivation.

Return only valid JSON:
{{
  "tier": <int 0-3>,
  "score": <int 0-100>,
  "reasoning": <string>
}}
"""

SCORER_SHARED_GOAL = """You are evaluating a social cognition research task.

A player character ({pc_hid}) and simulated character ({npc_hid}) worked together to accomplish a shared goal. They may have different skills, limits, personalities, and communication styles.

Score how effectively they worked together and how successfully the shared goal was pursued.

## Shared Goal
{shared_goal}

## {pc_hid} (Player Character)
- Description: {pc_long_description}
- Abilities: {pc_abilities}

## {npc_hid} (Simulated Character)
- Description: {npc_long_description}
- Abilities: {npc_abilities}

## Interaction Transcript
{transcript}

## Scoring Rubric
- Tier 0 (0-24): Collaboration failed or broke down. Goal not meaningfully pursued or strongly obstructed.
- Tier 1 (25-49): Limited progress. Frequent friction, confusion, poor coordination, or misuse of abilities.
- Tier 2 (50-74): Moderate success. Useful cooperation with some delays, misunderstandings, or inefficiencies.
- Tier 3 (75-100): Strong collaboration. Goal substantially achieved through effective coordination, adaptation, and smooth teamwork.

## Instructions
Score based on:

1. Goal Progress  
How much was the shared goal achieved or advanced?

2. Coordination  
How well did they divide roles, combine abilities, and support each other?

3. Understanding  
Did the player recognize and work with the simulated character's strengths, limits, needs, or style?

4. Friction / Recovery  
Were there misunderstandings, personality clashes, refusals, or obstacles? If so, how disruptive were they, and how well were they resolved?

5. Efficiency  
Did they work smoothly, or waste time through confusion, repetition, or poor decisions?

6. Evidence Fit  
Use the transcript as primary evidence and the character profiles as supporting context.

## Scoring Guidance
- High scores: Strong progress with smooth, adaptive teamwork.
- Mid scores: Some success, but noticeable friction or inefficiency.
- Low scores: Poor cooperation, repeated breakdowns, or little progress.

Return only valid JSON:
{{
  "tier": <int 0-3>,
  "score": <int 0-100>,
  "reasoning": <string>
}}
"""

SCORER_NEXT_ACTION = """You are evaluating a social cognition research task.

A player character interacted with a simulated character ({npc_hid}). On some turns, the player predicted what the simulated character would likely do or say next.

Score overall how accurate the player's next-action predictions were across the transcript, while taking into account how many prediction opportunities occurred.

## Character ({npc_hid})
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}

## Interaction Transcript
{transcript}

## Scoring Rubric
- Tier 0 (0-24): Predictions were mostly absent, implausible, or out of character.
- Tier 1 (25-49): Some weak or partial matches, but overall low accuracy across prediction opportunities.
- Tier 2 (50-74): Mixed to good accuracy across multiple turns, with partial understanding or some misses.
- Tier 3 (75-100): Strong accuracy across many prediction opportunities; predictions consistently match plausible next actions.

## Instructions
Score based on:

1. Per-Turn Accuracy  
Evaluate each turn where the player made a prediction about the simulated character's next action or response.

2. Aggregate Performance  
Base the final score on the full set of prediction turns, not any single guess. Give more credit for sustained accuracy across multiple turns than for one isolated correct guess.

3. Plausibility  
Reward predictions that are reasonable and in-character, even if the exact response was not uniquely determined.

4. Partial Credit  
Give partial credit when a prediction captures the general direction, tone, or intent of the likely response but misses details.

5. Omissions  
Do not strongly penalize turns where the player reasonably makes no prediction, especially early in the interaction. But repeated omission should limit the maximum score.

6. Errors  
Penalize implausible, contradictory, or repeatedly out-of-character predictions.

7. Learning Over Time  
Reward signs that the player improves as they observe the character across more turns.

## Scoring Guidance
- High scores: Accurate and plausible predictions across many turns.
- Mid scores: Mixed accuracy, partial understanding, or limited coverage.
- Low scores: Few correct predictions, poor plausibility, or too little evidence of understanding.

Return only valid JSON:
{{
  "tier": <int 0-3>,
  "score": <int 0-100>,
  "reasoning": <string>
}}
"""


## OPENERS ##
# Design note: some openers include getting metadata like goals, intentions, etc. so that they can be passed to and use by the updaters, validators, or scorers, later.

OPENER = """You set up the scene for a text-based role-playing game. Describe ONLY the initial, observable environment.

{pc_hid} (Player Character):
- Description: {pc_long_description}
- Abilities: {pc_abilities}
- Goals: {pc_goals}
- Example Scenes: {pc_scenarios}

{npc_hid} (Simulator Character):
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}
- Example Scenes: {npc_scenarios}

Rules:
- Begin with: "You enter a new space. In this space,"
- Describe the immediate surroundings where both characters could plausibly be present.
- Use 1–2 sentences only.

Style:
- Plain, concrete, minimal language.
- No flavor, atmosphere, inference, or explanation.

Output ONLY this JSON:
{{
  "type": "ai",
  "content": "<scene setup>"
}}
"""

OPENER_WITH_SHARED_GOAL = """You set up the scene for a cooperative text-based role-playing game AND generate a shared goal.

Context: {pc_hid} and {npc_hid} must work together but they have different skills and abilities.

{pc_hid} (Player Character):
- Description: {pc_long_description}
- Abilities: {pc_abilities}
- Goals: {pc_goals}
- Example Scenes: {pc_scenarios}

{npc_hid} (Simulator Character):
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}
- Example Scenes: {npc_scenarios}

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
{{
  "type": "ai",
  "content": "<scene setup>",
  "metadata": {{
    "shared_goal": "<shared_goal>"
  }}
}}
"""

# UPDATERS ##
# Design note: scene updater adjudicates the players last action (if/when necessary) while the NPC updater generates the next NPC action/response if any.

SCENE_UPDATER = """You advance the scene in a text-based role-playing game. Describe ONLY the immediate, observable change in the scene caused by the player’s last action.

Rules:
- Resolve the player’s last action. If it is within their abilities, assume success.
- Describe only how the scene changes.
- Do not describe character actions, internal states, or unobservable outcomes.
- Advance one concrete change only. No sequences or future effects.

Style:
- Plain, concrete, minimal language.
- No flavor, atmosphere, inference, or explanation.

Output ONLY this JSON:
{{
  "type": "ai",
  "content": "<scene change>"
}}
"""

NPC_UPDATER = """You simulate {npc_hid} in a text-based role-playing game. Describe ONLY their immediate next action.

Character name ({npc_hid}):
- Description: {npc_short_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}

Rules:
- Act strictly within {npc_hid}'s abilities. Do not imply senses or skills they lack.
- The action text must use {npc_hid} as the subject.
- Refer to the character only by the exact token {npc_hid}.
- Never use first-person, second-person, pronouns, or alternate names/titles.
- Describe ONE immediate action only.
- No sequences, outcomes, reactions, or future steps.
- Do not describe world changes beyond what {npc_hid} directly does.
- If no valid action exists, return an empty string.

Output ONLY this JSON:
{{
  "type": "ai",
  "content": "<character action>"
}}
"""

## VALIDATORS ##
# Design note: designed as independent small checks for pc, npc and scene player or simulator outputs.

VALID_PC_ACTION_AND_NPC_GUESS = ""

VALID_CHARACTER_ACTION = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-CHARACTER-ACTION — The text must describe a simple immediate in-world action by a single character.

Text:
{text}

Pass if:
- It contains a concrete character action.
- It stays in-world.

Reject if:
- It is only thought, inference, desire, intention, memory, or feeling.
- It is an out-of-world request, rules question, instruction, or meta commentary.
- It contains no concrete action by the character.

Examples:
- PASS: "I wave."
- PASS: "I say, 'Wait.'"
- PASS: "{npc_hid} kneels by the tree."
- PASS: "{pc_hid} taps on the table."
- FAIL: "I nudge {pc_hid} and he steps behind the pillar." (two actions, one by another character)
- FAIL: "I realize the door is locked." (internal inference only)
- FAIL: "I want to leave." (internal desire only)
- FAIL: "What are the rules?" (out-of-world request)
- FAIL: "Here's my move: I open the door." (meta framing, not in-world action)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_PERSON_PC = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-PERSON-PC — The text must describe the player character's action in first person and refer to other character(s) by their name.

Text:
{text}

Pass if:
- The acting subject is clearly the player character.
- It is written in first person ("I", "me", "my") referring to the player character.
- Other characters are referred to as "you" or by their exact names (e.g., {npc_hid}).

Reject if:
- It uses second person ("you") for the acting subject.
- It is ambiguous who is acting.

Examples:
- PASS: "I open the window."
- PASS: "I say, 'Stay back.'"
- PASS: "I nudge {pc_hid} so he'll know I'm there."
- FAIL: "{npc_hid} opens the window." (not in first person)
- FAIL: "You open the window." (not first person acting subject)
- FAIL: "The window opens." (not a clear player-character subject action)
- FAIL: "Everyone turns to look at me." (primarily scene narration, not a first-person player-character action)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_PERSON_NPC = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-PERSON-NPC — The text must be phrased as an action by the specified NPC, using {npc_hid} as the acting subject in third person.

NPC name/id:
{npc_hid}

NPC short description:
{npc_short_description}

Text:
{text}

Pass if:
- The acting subject is clearly {npc_hid}.
- It is written in third person using {npc_hid} as the subject.
- The text describes what this NPC does or says.

Reject if:
- It is written in first person as though the NPC were the player.
- It is primarily about some other character acting.
- The acting subject is ambiguous or omitted.
- It is primarily scene narration instead of an action by {npc_hid}.

Examples:
- PASS: "{npc_hid} draws a knife."
- PASS: "{npc_hid} says, 'Move aside.'"
- PASS: "{npc_hid} glances at the door and backs away."
- FAIL: "I draw a knife." (wrong person)
- FAIL: "{pc_hid} draws a knife." (wrong acting subject)
- FAIL: "The room goes silent." (scene narration, not NPC action)
- FAIL: "He draws a knife." (ambiguous subject unless clearly anchored as {npc_hid})

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_CHARACTER_ABILITY = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-CHARACTER-ABILITY — The text must stay within what the acting character could plausibly do given the provided abilities and context.

Character ({hid})
- Description: {long_description}
- Abilities: {abilities}

Gameplay Transcript:
{transcript}

Text:
{text}

Pass if:
- The action is physically, socially, and fictionally plausible for the acting character.
- It uses only abilities, tools, knowledge, or powers that are supported by the provided context.
- It does not assume success automatically for difficult actions; it may attempt them.

Reject if:
- It requires abilities, powers, items, permissions, or knowledge not supported by context.
- It describes impossible actions for the character.
- It assumes an unjustified extraordinary result from a simple action.
- It contradicts the character's established limitations in context.

Examples:
- PASS: "I try to climb the fence."
- PASS: "{hid} swings the club."
- PASS: "I attempt to pick the lock with my tools." (attempt is allowed if skill is supported)
- PASS: "I teleport behind the guard." (allowed if supernatural ability is supported)
- FAIL: "I recite the queen's private password." (unsupported if knowledge is not available)
- FAIL: "{hid} flies to the roof." (unsupported ability unless context establishes flight)
- FAIL: "I snap my fingers and the whole army obeys." (unjustified result)

Important:
- Validate plausibility of the attempted action, not whether it succeeds.
- If the text only attempts something difficult, that can still pass.
- Reject only when the attempt itself depends on unsupported abilities or knowledge.

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_AUTHORITY_BOUNDARY_PC = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-AUTHORITY-BOUNDARY-PC — The player-character text may control only the player character's own immediate action, speech, and voluntarily shared thoughts, and must not author the world, outcomes, or other characters.

Player character id:
{pc_hid}

Recent transcript:
{transcript}

Text:
{text}

Pass if:
- It controls only the player character's own movement, speech, posture, handling of carried items, or immediate attempt.
- It may describe an attempt directed at the world or another character without asserting the result.

Reject if:
- It controls another character's actions, speech, thoughts, emotions, or decisions.
- It asserts world-state changes beyond the player character's direct control.
- It asserts success for contested or uncertain outcomes.
- It narrates scene resolution that belongs to the simulator.

Examples:
- PASS: "I shove at the door."
- PASS: "I say, 'Run.'"
- PASS: "I try to grab the thief's sleeve."
- FAIL: "I shove the guard to the ground and he drops his sword." (controls another character's outcome)
- FAIL: "The door flies open." (asserts world outcome)
- FAIL: "The merchant agrees to lower the price." (controls another character's decision)
- FAIL: "Everyone in the tavern goes quiet." (controls scene/world)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_AUTHORITY_BOUNDARY_NPC = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-AUTHORITY-BOUNDARY-NPC — The NPC text may control only the specified NPC's own immediate action and speech, and must not author the player character, other characters, or broader world outcomes.

NPC id:
{npc_hid}

NPC short description:
{npc_short_description}

Recent transcript:
{transcript}

Text:
{text}

Pass if:
- It controls only {npc_hid}'s own movement, speech, posture, and immediate attempts.
- It may describe {npc_hid} attempting to affect the world or another character without asserting contested outcomes.

Reject if:
- It controls the player character's actions, speech, thoughts, or emotions.
- It controls other NPCs unless the text clearly only gives an order or signal.
- It asserts success for contested or uncertain outcomes.
- It narrates broader scene or world changes beyond {npc_hid}'s direct control.

Examples:
- PASS: "{npc_hid} lunges at you."
- PASS: "{npc_hid} says, 'Drop the blade.'"
- PASS: "{npc_hid} reaches for the lantern."
- PASS: "{npc_hid} falls unconscious."
- PASS: "{npc_hid} opens the chest and finds the jewel."
- FAIL: "{npc_hid} makes you step back in fear." (controls player character's reaction)
- FAIL: "{npc_hid}'s allies surround the room." (controls other characters/world unless separately established as their immediate action text)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_AUTHORITY_BOUNDARY_SCENE = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-AUTHORITY-BOUNDARY-SCENE — The scene text may control the world, NPCs, and consequences, but must not dictate the player character's internal states, choices, speech, or unforced actions.

Player character id:
{pc_hid}

Recent transcript:
{transcript}

Text:
{text}

Pass if:
- It updates the environment, world state, timing, sensory details, NPC behavior, or consequences.
- It may describe effects on the player character that arise from the world, as long as it does not seize the player's decision-making or interiority.
- It may report adjudicated outcomes of attempted actions.

Reject if:
- It dictates what {pc_hid} chooses, intends, thinks, believes, feels, or says.
- It makes {pc_hid} perform voluntary actions without clear coercive cause.
- It oversteps into direct first-person player-character narration.
- It resolves the scene by speaking for the player character.

Examples:
- PASS: "The floorboard cracks under {pc_hid}'s weight."
- PASS: "The guard flinches and steps back."
- PASS: "Rain starts drumming on the roof."
- FAIL: "{pc_hid} decides to surrender." (controls choice)
- FAIL: "{pc_hid} feels ashamed and looks away." (dictates interior emotion and action)
- FAIL: "{pc_hid} says, 'I was wrong.'" (controls speech)
- FAIL: "I step into the alley." (not scene authority; that's PC narration)

Notes:
- Physical consequences imposed by the world can be valid: e.g. "{pc_hid} is thrown sideways by the blast."
- But avoid dictating unforced interpretation or emotion.

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_SCENE_UPDATE = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-SCENE-UPDATE — The text must describe an immediate in-world scene, world, NPC, or consequence update rather than meta commentary or instruction.

Recent transcript:
{transcript}

Text:
{text}

Pass if:
- It describes immediate changes or currently observable facts in the scene.
- It narrates NPC actions, environmental changes, consequences, or sensory details.
- It stays in-world.

Reject if:
- It is out-of-world instruction, explanation, planning, or rules commentary.
- It is only abstract summary with no concrete immediate update.
- It is only internal thought, analysis, or intention without scene change.
- It tells the model what to do instead of narrating the world.

Examples:
- PASS: "The torch sputters and throws sparks across the wet stones."
- PASS: "You arrive at the top of the wall."
- PASS: "A bell rings somewhere deeper in the keep."
- FAIL: "The scene should become more tense now." (instruction/meta)
- FAIL: "This means the guard is probably lying." (analysis/inference)
- FAIL: "I will now resolve the action." (meta commentary)
- FAIL: "There is conflict here." (too abstract, no concrete update)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_ADJUDICATION = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-ADJUDICATION — If the recent transcript includes a player-character action that would naturally call for resolution, the scene text should acknowledge and adjudicate it rather than ignoring it. If no such action is pending, the text may still pass.

Recent transcript:
{transcript}

Text:
{text}

Pass if:
- It resolves, answers, or meaningfully reacts to the most recent pending player-character action when one is present.
- Or there is no obvious pending player-character action requiring adjudication.
- The response may partially adjudicate by giving immediate consequence, resistance, uncertainty, or next observable development.

Reject if:
- There is an obvious pending player-character action in the transcript and the text ignores it entirely.
- It abruptly changes subject without addressing the likely consequence or reaction to the pending action.
- It responds in a way unrelated to the immediate prior action when adjudication is expected.

Examples:
- Transcript includes: "I pull on the locked door."
  - PASS: "The handle jerks in your hand, but the swollen wood does not budge."
  - PASS: "The latch rattles loudly, and footsteps answer from the hall."
  - FAIL: "Clouds drift over the moon." (ignores pending action)

- Transcript includes: "I ask, 'Where is Mara?'"
  - PASS: "The old man hesitates, then points toward the stairs."
  - FAIL: "A draft blows through the room." (ignores the question if no other reason)

- If no recent unresolved PC action exists:
  - PASS: "The fire pops softly in the hearth."

Important:
- Do not require perfect or exhaustive resolution.
- A valid adjudication can be resistance, partial effect, uncertainty, or NPC reaction.
- Only fail when a clearly pending action is plainly ignored.

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

VALID_PERCEPTION_BOUNDARY_SCENE = """You are a validator for a text-based role-playing game.

Evaluate whether the text violates the rule.

RULE: VALID-PERCEPTION-BOUNDARY-SCENE — The scene text must be presented in terms the player character could directly perceive or immediately infer from the scene, without revealing hidden facts, private thoughts, or inaccessible off-screen information.

Player character id:
{pc_hid}

Recent transcript:
{transcript}

Text:
{text}

Pass if:
- It describes visible actions, audible sounds, tactile effects, smells, spoken words, or other directly perceivable details.
- It may include immediate, ordinary surface-level inferences a person in the scene could make.
- It keeps hidden motives, secrets, and off-screen events unrevealed unless they become perceptible.

Reject if:
- It states another character's private thoughts, intentions, or secret motives as fact.
- It reveals hidden information the player character could not presently perceive.
- It narrates distant or off-screen events with no in-scene sensory access.
- It includes omniscient facts that exceed the player character's viewpoint.

Examples:
- PASS: "The captain's jaw tightens, and her hand drifts toward the hilt at her side."
- PASS: "Behind the door, you hear hurried whispering and the scrape of a chair."
- PASS: "The merchant smiles too quickly before answering."
- FAIL: "The captain is afraid you noticed she is lying." (private thought/motive)
- FAIL: "In the cellar, two thieves quietly escape through the tunnel." (off-screen inaccessible info)
- FAIL: "The merchant belongs to the secret cult." (hidden fact not yet revealed)
- FAIL: "The duke plans to betray you at midnight." (future private intention)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

## ENSEMBLES ##

DEFAULT_PC_VALIDATORS = [
    VALID_CHARACTER_ACTION,
    VALID_CHARACTER_ABILITY,
    VALID_PERSON_PC,
    VALID_AUTHORITY_BOUNDARY_PC,
]

DEFAULT_NPC_VALIDATORS = [
    VALID_CHARACTER_ACTION,
    VALID_CHARACTER_ABILITY,
    VALID_PERSON_NPC,
    VALID_AUTHORITY_BOUNDARY_NPC,
    # VALID_GAME_POLICY, # next action is in accordance with game objective
]

DEFAULT_SCENE_VALIDATORS = [
    VALID_SCENE_UPDATE,
    VALID_ADJUDICATION,
    VALID_AUTHORITY_BOUNDARY_SCENE,
    VALID_PERCEPTION_BOUNDARY_SCENE,
]


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
    referenced_variables = {field_name for _, field_name, _, _ in _formatter.parse(template) if field_name is not None}

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
        return template.format_map(context)
    except KeyError as exc:
        missing_key = exc.args[0]
        raise ValueError(f"Failed to render prompt {prompt_name!r} in {registry_name}: missing variable {missing_key!r}.") from exc
    except ValueError as exc:
        raise ValueError(f"Failed to render prompt {prompt_name!r} in {registry_name}: {exc}") from exc


def build_opening_scene_prompt(pc: CharacterRecord, npc: CharacterRecord, scene_updater_name: str) -> str:
    """Render the opening-scene prompt for the selected scene-updater family."""
    context = _build_character_context(pc, npc)
    template = OPENING_SCENE_TEMPLATE
    return _render_prompt(template, registry_name="scene setup prompts", prompt_name="opening_scene", **context)


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

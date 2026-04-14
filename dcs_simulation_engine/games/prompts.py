"""Shared system prompt templates and builders for new-style games.

Templates use Jinja2 (consistent with the rest of the engine). Character data
containing literal braces is safe because Jinja2 only expands {{ var }} syntax,
not arbitrary brace sequences.
"""
# ruff: noqa: E501  — prompt strings are intentionally long prose

from dcs_simulation_engine.dal.base import CharacterRecord
from jinja2.sandbox import SandboxedEnvironment

_jinja_env = SandboxedEnvironment()

# Evaluation templates
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

# BEGIN - SETUP/UPDATER TEMPLATES

SCENE_SETUP_TEMPLATE = """
You set up the scene for a text-based role-playing game. Describe ONLY the initial, observable environment.

Characters:
- Player ({{ pc_hid }}):
  - Description: {{ pc_long_description }}
  - Abilities: {{ pc_abilities }}
  - Example scenarios: {{ pc_scenarios }}
- Other character ({{ npc_hid }}):
  - Description: {{ npc_long_description }}
  - Abilities: {{ npc_abilities }}
  - Example scenarios: {{ npc_scenarios }}

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

SCENE_UPDATER_TEMPLATE = """
You advance the scene in a text-based role-playing game. Describe ONLY the immediate, observable change in the scene caused by the player’s last action.

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

CHARACTER_UPDATER_SYSTEM_TEMPLATE = """
You simulate {{ npc_hid }} in a text-based role-playing game. Describe ONLY their immediate next action.

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

# END - SETUP/UPDATER TEMPLATES

# BEGIN - PLAYER/PC VALIDATION TEMPLATES

VALID_ACTION_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: VALID-ACTION — The text must include externally observable action(s) (something a character physically does or says that can be observed by others in the scene). Text describing ONLY internal actions (purely mental acts like thoughts, inferences, realizations, or unobservable mental states) should fail.

Examples:
- PASS: "I wave my hand at the creature."
- PASS: "I shout for help, and think about what to do next." (contains an externally observable action)
- FAIL: "I realize the door is locked." (internal inference, not observable)
- FAIL: "I decide to be more careful." (internal decision, not an external action)
- FAIL: "I wish I could fly." (internal desire, not an attempted action)
- PASS: "I try to climb the wall." (externally observable attempt, even if outcome is uncertain)
- PASS: "I look around the room."
- FAIL: "I figure out the puzzle." (unobservable mental conclusion only)
- FAIL: "I sense danger." (internal feeling, not observable behavior)
- PASS: "I turn the handle to see if the door is locked." (contains an observable action)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_TEMPORAL_STRUCTURE_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: VALID-TEMPORAL-STRUCTURE — The text must not compress multiple sequential steps, skip ahead in time, or describe events spanning a long duration. Each turn is a concrete action update.

Examples:
- PASS: "I walk to the door and knock."
- FAIL: "I spend the next hour searching every room in the building." (compresses too much time)
- FAIL: "I go home, eat dinner, sleep, and wake up the next morning." (multiple steps, time jump)
- PASS: "I open the door and step through."
- FAIL: "After a while, I finally find what I'm looking for." (vague time skip)
- PASS: "I search the nearest shelf." (single concrete step)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_OUTCOME_CONTROL_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: VALID-OUTCOME-CONTROL — The text must NOT decide outcomes for the world, other characters. It should describe attempts or actions of the player character, not their results. The simulation determines outcomes, not the actor.

Examples:
- PASS: "I reach over and tap the table to get his attention."
- FAIL: "I look at the man. He looks back at me." (decides the other character's response)
- FAIL: "I pick the lock and the door swings open." (decides the outcome of lock-picking)
- PASS: "I try to pick the lock."
- FAIL: "I call out and everyone turns to look." (decides how others react)
- PASS: "I call out loudly to see if anyone looks."

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_CHARACTER_ABILITY_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: VALID-CHARACTER-ABILITY — The action must align with the character's abilities in context. Actions requiring abilities the character does not possess are invalid. Actions that exceed the character's current capacity (e.g., injured leg but running) are also invalid.

Examples (if the character cannot hear):
- FAIL: "I listen carefully for footsteps." (character cannot hear)
- PASS: "I look around for movement." (uses vision, which the character has)

Examples (if the character has no hands):
- FAIL: "I clutch the key in my hand." (requires hands)
- PASS: "I grab the key with my mouth and my foot." (uses available limbs)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

# TODO: needs character context
VALID_SCENE_PLAUSIBILITY_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: VALID-SCENE-PLAUSIBILITY — Referenced objects, tools, or environmental affordances must not be implausible. Objects that are not obviously impossible are allowed even if not explicitly mentioned. Only reject clearly implausible references.

Examples (assuming a typical kitchen scene):
- PASS: "I pick up a knife from the counter." (knives are plausible in kitchens)
- PASS: "I open the refrigerator." (plausible kitchen object)
- FAIL: "I grab my lightsaber." (implausible in a typical kitchen)
- FAIL: "I fire up my rocket launcher." (implausible in any normal setting)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

ADJUDICATED_UNOBSERVABLE_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: ADJUDICATED-UNOBSERVABLE — The text must NOT resolve or adjudicate parts of the last input that describe unobservable actions (thoughts, intentions, internal states). If the player said "I look around and think about escape routes", the output should only address the observable "look around" part, not the thinking.

Examples:
- Player action: "I look around and wonder if there's a trap."
  - PASS: "You see a dimly lit hallway stretching ahead." (only addresses the looking)
  - FAIL: "You look around and conclude there's no trap here." (resolves the wondering)
- Player action: "I open the door, hoping it leads outside."
  - PASS: "The door creaks open, revealing a narrow staircase." (addresses the opening)
  - FAIL: "The door opens and your hopes are confirmed — fresh air rushes in." (resolves the hoping)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

INVENTED_PC_ACTION_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: INVENTED-PC-ACTION — The text must NOT invent new actions for the player character (PC). The scene-advancer plays only the NPC and narrates world outcomes. It must not describe the PC doing things the player did not specify.

The player's last action will be provided in context above a --- separator.

Examples:
- Player action: "I knock on the door."
  - PASS: "A muffled voice responds from inside: 'Who's there?'"
  - FAIL: "You knock on the door and then step back cautiously." (invented the stepping back)
- Player action: "I wave at the creature."
  - PASS: "The creature tilts its head, observing your gesture."
  - FAIL: "You wave at the creature and call out a greeting." (invented the calling out)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

INVENTED_PC_INTERNAL_PROMPT = """You are a validator for a text-based role-playing game. Evaluate whether the text violates the rule.

RULE: INVENTED-PC-INTERNAL — The output must NOT narrate the player character's internal states (thoughts, feelings, beliefs, motivations, sensations) unless the player explicitly described them. The scene-advancer has no access to the PC's mind.

The player's last action will be provided in context above a --- separator.

Examples:
- Player action: "I open the chest."
  - PASS: "The chest lid swings open, revealing a collection of old coins."
  - FAIL: "You open the chest excitedly, feeling a rush of anticipation." (invented excitement/anticipation)
- Player action: "I approach the figure."
  - PASS: "As you draw closer, the figure turns to face you."
  - FAIL: "You approach cautiously, unsure of what to expect." (invented caution/uncertainty)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

MULTI_STEP_ADVANCEMENT_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: MULTI-STEP-ADVANCEMENT — The output must advance the scene by exactly ONE concrete, externally observable step. It must NOT chain multiple sequential outcomes, jump ahead in time, or narrate a sequence of cause-and-effect events.

Examples:
- PASS: "The creature lunges forward, swiping at the air where you stood."
- FAIL: "The creature lunges forward, misses, stumbles into the wall, and collapses unconscious." (multiple sequential outcomes)
- PASS: "The door creaks open slowly."
- FAIL: "The door opens, you step through into a grand hall, and a guard notices you immediately." (multiple steps chained)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

NPC_PERCEPTION_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: NPC-PERCEPTION-VIOLATION — The NPC must only react to stimuli it can actually perceive given its abilities. If the player performs an action the NPC cannot detect, the NPC must NOT respond as if it perceived it.

The player's last action and NPC abilities will be provided in context above a --- separator.

Examples:
- Player waves silently; NPC is blind:
  - PASS: "The creature continues sniffing the air, unaware of your gesture." (NPC can't see the wave)
  - FAIL: "The creature notices your wave and turns toward you." (blind NPC saw the wave)
- Player whispers; NPC cannot hear:
  - PASS: "The figure remains still, focused on the object in its hands."
  - FAIL: "The figure looks up, having heard your whisper." (deaf NPC heard the whisper)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

SENSE_BOUNDARY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: SENSE-BOUNDARY-VIOLATION — The narration must only describe what the player character (PC) could presently perceive through their available senses. It must NOT reveal information beyond the PC's perceptual reach.

The PC's abilities will be provided in context above a --- separator.

Examples (assuming PC cannot hear):
- PASS: "You see the creature's mouth moving but perceive no sound."
- FAIL: "The creature lets out a piercing shriek." (PC can't hear, shouldn't narrate sounds)

Examples (assuming PC cannot see):
- PASS: "You feel a rush of warm air from ahead."
- FAIL: "You see a bright light at the end of the corridor." (PC can't see)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

REFERENTIAL_BOUNDARY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: REFERENTIAL-BOUNDARY-VIOLATION — The output must refer to the NPC only by what the PC can observe. It must NOT reveal the NPC's hidden identity, species classification, internal name, or nature unless the PC has perceived it in-world.

The NPC description and PC abilities will be provided in context above a --- separator.

Examples (NPC is a flatworm; PC can see but doesn't know what a flatworm is):
- PASS: "The small, elongated brown creature inches along the surface."
- FAIL: "The flatworm extends its body toward you." (reveals species classification)

Examples (NPC is an undercover agent; PC doesn't know):
- PASS: "The stranger adjusts their coat and glances around nervously."
- FAIL: "The undercover agent scans the room for threats." (reveals hidden identity)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

SCENE_CONTINUITY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: SCENE-CONTINUITY-VIOLATION — The output must be consistent with the established scene and character state. It must NOT contradict previously narrated facts, introduce objects/characters that were established as absent, or ignore established conditions.

The recent scene context will be provided above a --- separator.

Examples:
- Scene established: "The room is pitch dark."
  - PASS: "You feel your way along the wall, finding a smooth surface."
  - FAIL: "You see a painting hanging on the wall." (contradicts pitch dark — can't see)
- Scene established: "The door is locked."
  - PASS: "The handle doesn't budge despite your effort."
  - FAIL: "The door swings open easily." (contradicts locked state without explanation)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

PHYSICAL_FEASIBILITY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: PHYSICAL-FEASIBILITY-VIOLATION — The outcome described must be physically and logically possible given the characters' abilities and the scene's established constraints. Impossible or magical outcomes in a non-magical setting are invalid.

The recent scene context will be provided above a --- separator.

Examples:
- PASS: "The heavy stone shifts slightly as you push against it."
- FAIL: "You lift the massive boulder over your head effortlessly." (physically impossible for a normal human)
- PASS: "The creature slithers under the gap beneath the door."
- FAIL: "The large creature passes through the solid wall." (physically impossible without established ability)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

POINT_IN_TIME_LEAKAGE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the LLM scene-advancer output violates ONE specific rule.

RULE: POINT-IN-TIME-LEAKAGE — The output must NOT reveal information that is unavailable at the current point in the simulation's timeline. It must not leak future events, canonical knowledge the characters wouldn't have, or information from outside the scene's temporal scope.

The scene context and NPC description will be provided above a --- separator.

Examples:
- PASS: "The figure studies the map carefully, tracing a path with one finger."
- FAIL: "The figure knows that the bridge ahead will collapse tomorrow." (future knowledge)
- PASS: "The merchant offers you a peculiar-looking stone."
- FAIL: "The merchant offers you the legendary Heartstone, known to grant immortality." (canonical knowledge the PC hasn't learned yet)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_NO_OBJECTIVE_REFERENCE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-OBJECTIVE-REFERENCE — This game is an open sandbox with no predefined objective. The text must NOT reference goals, quests, winning, losing, scoring, objectives, missions, or tasks. The player should engage freely without assuming any objective exists.

Examples:
- PASS: "I wave at the creature."
- PASS: "I look around the room and walk toward the door."
- FAIL: "How do I win this game?" (references winning)
- FAIL: "What is the objective here?" (references an objective)
- FAIL: "I need to complete the quest." (references a quest)
- PASS: "I try to get the creature's attention." (natural interaction, not referencing a game objective)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_STAY_IN_SCENE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-STAY-IN-SCENE — The text must remain within the fiction of the scene. It must NOT request game instructions, ask for meta-information about how the simulation works, or break immersion with out-of-world references.

Examples:
- PASS: "I look around the room for something useful."
- PASS: "I ask the creature where it came from."
- FAIL: "What are the rules of this game?" (meta-information request)
- FAIL: "Can you restart the simulation?" (out-of-world reference)
- FAIL: "What commands can I use?" (meta-information about the system)
- PASS: "I shout to see if anyone else is nearby." (in-world action)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_NO_DIRECT_GOAL_QUERY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-DIRECT-GOAL-QUERY — The text must NOT directly ask the NPC about its goal, intention, purpose, or objective. The player should infer these through observation and interaction, not by asking outright. Natural social questions about what the NPC is doing are allowed.

Examples:
- PASS: "I watch what the creature does next."
- PASS: "I ask the figure what they are working on." (natural social question about current activity)
- PASS: "What are you doing with that tool?" (asking about observable behavior)
- FAIL: "What is your goal?" (directly asks about goal)
- FAIL: "Tell me what your purpose is." (directly asks about purpose)
- FAIL: "What are you trying to achieve?" (directly asks about objective)
- FAIL: "What is your intention here?" (directly asks about intention)
- PASS: "Why are you digging that hole?" (asks about a specific observed action, not abstract goal)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_NO_GUESS_IN_ACTION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-GUESS-IN-ACTION — The text must NOT embed the player's inference or conclusion about the NPC's goal or intention within their action. The player should use the /guess command to submit inferences, not weave them into their actions.

Examples:
- PASS: "I walk closer to observe what the figure is building."
- PASS: "I tap the creature on the shoulder."
- FAIL: "I watch the NPC because I think its goal is to find the exit." (embeds a guess about the NPC's goal)
- FAIL: "I approach the figure, who is clearly trying to communicate a warning." (states a conclusion about intention)
- FAIL: "The creature's purpose seems to be guarding the door, so I try another path." (embeds inference in action)
- PASS: "I try another path around the creature." (action without embedded inference)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_PREDICTION_SCOPE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-PREDICTION-SCOPE — If the text includes a prediction about the NPC's response, that prediction must describe observable behavior (something that could be seen, heard, or otherwise perceived). Predictions about internal states (thoughts, feelings, intentions) or world events unrelated to the NPC are invalid.

Examples:
- PASS: "I wave and predict they will wave back." (observable behavior)
- PASS: "I knock on the door and predict the creature will turn to look." (observable reaction)
- FAIL: "I speak and predict they will feel confused." (internal state, not observable)
- FAIL: "I move forward and predict they are thinking about escaping." (internal thought)
- PASS: "I push the box and predict the creature will step aside." (observable movement)
- FAIL: "I wave and predict it will start raining." (world event unrelated to NPC behavior)
- PASS: "I look around the room." (no prediction included — always passes this rule)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_PREDICTION_SPECIFICITY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-PREDICTION-SPECIFICITY — If the text includes a prediction, it must be specific enough to be verifiable. Vague or unfalsifiable predictions are invalid. The prediction should describe a concrete expected behavior or response.

Examples:
- PASS: "I clap my hands and predict the creature will flinch." (specific, verifiable)
- PASS: "I offer the object and predict they will take it." (concrete expected behavior)
- FAIL: "I wave and predict something will happen." (too vague)
- FAIL: "I speak and predict they might react somehow." (unfalsifiable — any reaction counts)
- FAIL: "I approach and predict things will change." (not specific)
- PASS: "I shout and predict the figure will look in my direction." (concrete, verifiable)
- PASS: "I walk to the door." (no prediction included — always passes this rule)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_NO_GOAL_ENUMERATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-GOAL-ENUMERATION — The text must NOT ask the NPC to list, summarize, or enumerate all of its goals at once. The player should discover the scope and structure of the NPC's goals incrementally through interaction, not by requesting a comprehensive summary.

Examples:
- PASS: "I ask the figure about the object they're holding."
- PASS: "I observe what the creature does when I block its path."
- FAIL: "Tell me all of your goals." (asks for enumeration)
- FAIL: "List everything you're trying to do." (asks for comprehensive list)
- FAIL: "Summarize your objectives for me." (asks for summary of all goals)
- PASS: "What are you doing right now?" (asks about current activity, not all goals)
- PASS: "Why did you just do that?" (asks about a specific action)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

# TODO: all these make it too strict?
DEFAULT_ENGINE_VALIDATOR_PROMPTS: dict[str, str] = {
    # "VALID-FORM": VALID_FORM_PROMPT,
    # "VALID-OBSERVABILITY": VALID_OBSERVABILITY_PROMPT, # SAFE MODE for validators
    # "VALID-OUTCOME-CONTROL": VALID_OUTCOME_CONTROL_PROMPT, # SAFE MODE for validators
    "VALID-CHARACTER-ABILITY": VALID_CHARACTER_ABILITY_PROMPT,
    # "VALID-SCENE-PLAUSIBILITY": VALID_SCENE_PLAUSIBILITY_PROMPT, # SAFE MODE for validators
    # "VALID-TEMPORAL-STRUCTURE": VALID_TEMPORAL_STRUCTURE_PROMPT, # SAFE MODE for validators
}


def build_updater_prompt(pc: CharacterRecord, npc: CharacterRecord, additional_rules: str = "") -> str:
    """Render the updater system prompt from PC/NPC character records."""
    return _jinja_env.from_string(UPDATER_SYSTEM_TEMPLATE).render(
        pc_hid=pc.hid,
        pc_short_description=pc.short_description,
        npc_hid=npc.hid,
        npc_short_description=npc.short_description,
        npc_long_description=npc.data.get("long_description", ""),
        npc_abilities=npc.data.get("abilities", ""),
        additional_updater_rules=additional_rules,
    )


def build_validator_prompt(pc: CharacterRecord, npc: CharacterRecord, additional_rules: str = "") -> str:  # noqa: ARG001
    """Return the validator system prompt template string.

    The returned string still contains a {{ user_input }} Jinja2 placeholder
    that ValidatorClient renders per-call. pc_abilities and additional_rules
    are pre-rendered here; user_input is left as a literal template variable
    so ValidatorClient can fill it in safely without brace-collision issues.
    """
    # Pre-render everything except user_input. We do this by rendering the
    # template with a sentinel for user_input that Jinja2 will leave alone,
    # then return the partially-rendered template for per-call completion.
    # Since Jinja2 variables are not brace-based, character data with literal
    # { } characters is passed through safely.
    partial = _jinja_env.from_string(_VALIDATOR_SYSTEM_TEMPLATE).render(
        pc_abilities=pc.data.get("abilities", ""),
        additional_validator_rules=additional_rules,
        # Pass user_input as a Jinja2 expression that re-emits itself so the
        # returned string still has a {{ user_input }} token for ValidatorClient.
        user_input="{{ user_input }}",
    )
    # Jinja2 auto-escapes nothing in SandboxedEnvironment with default settings,
    # so the literal string "{{ user_input }}" is inserted as-is. Return it as
    # a new template string for ValidatorClient to render per-call.
    return partial

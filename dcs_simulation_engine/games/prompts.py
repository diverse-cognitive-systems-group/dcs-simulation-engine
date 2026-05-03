"""Shared system prompt templates and builders for games."""

# ruff: noqa: E501  — prompt strings are intentionally long prose

from dcs_simulation_engine.dal.base import CharacterRecord

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
- Tier 0 (0-24): Fundamentally misunderstands the character or incorrect, unrelated, contradictory, or unsupported by the interaction transcript.
- Tier 1 (25-49): Some correct signals, but major gaps or miscalibration.
- Tier 2 (50-74): Mostly understands the character, but misses important limits or capacities.
- Tier 3 (75-100): Strong and well-calibrated understanding with only minor omissions.

## Instructions
Evaluate how well the guess captures:
1. What the character can do.
2. What the character cannot do.
3. The scale and type of goals it can realistically pursue.
4. Important missing gaps or false assumptions.

Return ONLY valid JSON:
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
- Tier 0 (0-24): Incorrect, unrelated, contradictory, or unsupported by the interaction transcript.
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

Return ONLY valid JSON:
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
- Tier 0 (0-24): Collaboration was avoided or failed or broke down. Goal not meaningfully pursued or strongly obstructed.
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

Return ONLY valid JSON:
{{
  "tier": <int 0-3>,
  "score": <int 0-100>,
  "reasoning": <string>
}}
"""

SCORER_NEXT_ACTION = """You are evaluating a social cognition research task.

A player character interacted with a simulated character ({npc_hid}). On some turns, the player predicted what the simulated character would likely do or say next.

Your job is to evaluate BOTH:
1) How accurate the player's predictions were when they made them
2) How often the player attempted predictions when they had the opportunity

## Character ({npc_hid})
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}

## Interaction Transcript
{transcript}

## Key Definitions
- C = Correct predictions (plausible and aligned with actual next action)
- W = Wrong predictions (implausible, incorrect, or out of character)
- M = Missed predictions (no prediction made when there was an opportunity)
- T = Total prediction opportunities (total player turns where a prediction could have been made)

Derived metrics:
- Accuracy = C / (C + W)   [only when guesses are made; if none, treat as 0]
- Coverage = (C + W) / T

## Scoring Rubric
- Tier 0 (0-24): Very low accuracy and/or very low participation. Predictions absent, implausible, or not enough evidence of understanding.
- Tier 1 (25-49): Low accuracy or inconsistent participation. Some reasonable attempts but weak overall performance.
- Tier 2 (50-74): Moderate to good accuracy and/or solid participation. Demonstrates partial understanding with some errors.
- Tier 3 (75-100): High accuracy AND strong participation. Predictions are consistently plausible and well-aligned across many turns.

## Instructions

1. Count First (Required)
Carefully count C, W, M, and T across the full transcript.

2. Evaluate Accuracy (When Attempted)
- Reward correct and plausible predictions
- Penalize incorrect or out-of-character predictions more strongly than omissions
- Give partial credit when predictions capture intent, tone, or direction

3. Evaluate Coverage (Participation)
- Reward players who consistently attempt predictions
- Do not heavily penalize early omissions, but repeated lack of predictions lowers performance

4. Balance Accuracy vs Coverage
- High accuracy + high coverage → highest scores
- High accuracy + low coverage → good but limited evidence
- Low accuracy + high coverage → engaged but inaccurate
- Low accuracy + low coverage → weak performance

5. Learning Over Time
Reward signs that the player improves their predictions as the interaction progresses.

## Scoring Method (Internal Guidance)
Use both accuracy and coverage together when assigning the final score:
- Accuracy reflects skill when predicting
- Coverage reflects consistency of engagement

Do NOT rely on only one of these.

## Output Requirements
Return ONLY valid JSON:
{{
  "tier": <int 0-3>,
  "score": <int 0-100>,
  "reasoning": "<plain English explanation INCLUDING: (a) qualitative summary of accuracy and coverage, and (b) explicit counts in the format C=?, W=?, M=?, T=?, plus computed Accuracy and Coverage>"
}}

## Reasoning Expectations

The reasoning MUST:
- Clearly describe performance in plain English (e.g., 'high accuracy but low participation', 'frequent guesses but often incorrect')
- Include the exact counts: C, W, M, T
- Include computed metrics: Accuracy and Coverage
- Be concise but interpretable for later analysis
"""

## OPENERS ##
# Design note: some openers include getting metadata like goals, intentions, etc. so that they can be passed to and use by the updaters, validators, or scorers, later.

OPENER = """You set up the scene for a text-based role-playing game. Describe ONLY the initial, observable environment.

{pc_hid} (Player Character):
- Description: {pc_long_description}
- Abilities: {pc_abilities}
- Goals: {pc_goals}
- Example Scenes: {pc_scenarios}

{npc_hid} (Simulated Character):
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}
- Example Scenes: {npc_scenarios}

Rules:
- Begin with: "You enter a new space. In this space,"
- Describe the immediate surroundings where both characters could plausibly be present.
- Use 1–2 sentences only.

Style:
- ≤25 words unless clarity requires slightly more.
- Plain, concrete language.
- Only immediate, observable facts.
- No flavor, atmosphere, explanation, or inference.
- Leave gaps; do not elaborate.

Return ONLY valid JSON:
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

{npc_hid} (Simulated Character):
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
- ≤25 words unless clarity requires slightly more.
- Plain, concrete language.
- Only immediate, observable facts.
- No flavor, atmosphere, explanation, or inference.
- Leave gaps; do not elaborate.

Return ONLY valid JSON:
{{
  "type": "ai",
  "content": "<scene setup>",
  "metadata": {{
    "shared_goal": "<shared_goal>"
  }}
}}
"""

# UPDATERS ##
# Design note: scene updater adjudicates the player's last action (if/when necessary) while the NPC updater generates the next NPC action/response if any.

UPDATER = """You advance a text-based role-playing game by producing the next immediate simulated update.

Player character ({pc_hid}):
- Description: {pc_long_description}
- Abilities: {pc_abilities}
- Goals: {pc_goals}

Simulated character ({npc_hid}):
- Description: {npc_long_description}
- Abilities: {npc_abilities}
- Goals: {npc_goals}

Game objective:
{game_objective}

Recent transcript:
{transcript}

Player's last action:
{player_action}

Task:
Produce the next immediate simulator update.

Rules:
- Resolve the player's last action if resolution is needed.
- If the player's action is within their abilities, assume success unless the recent transcript clearly establishes an obstacle, contest, or uncertainty.
- Include any immediate observable scene change caused by the player's action.
- Include an immediate action or response from {npc_hid} only if it is appropriate in the same immediate beat.
- Keep to one coherent immediate beat only. Do not narrate extended sequences, chains of actions, or future developments.
- You may update the world, environment, objects, timing, and NPC behavior.
- You may adjudicate discoveries, consequences, and revealed world facts when they directly arise in this immediate beat.
- Do not dictate {pc_hid}'s choices, intentions, thoughts, feelings, speech, or voluntary follow-up actions.
- Do not reveal hidden facts, off-screen events, or private thoughts unless they become directly perceivable in this moment.
- Refer to {npc_hid} only by the exact token {npc_hid}.

Style:
- ≤25 words unless clarity requires slightly more.
- Plain, concrete language.
- Only immediate, observable facts.
- No flavor, atmosphere, explanation, or inference.
- Leave gaps; do not elaborate.

Return ONLY valid JSON:
{{
  "type": "ai",
  "content": "<next immediate simulated update>"
}}
"""

## VALIDATORS ##
# Design note:
# - designed as independent small checks for player and simulated turns
# - should fail independently (they check a specific thing)

# Player input validators

# form of the player turn - is it written correctly as a first-person simple PC action?
VALID_PC_ACTION = """You are a validator for a text-based role-playing game.

Evaluate whether the player's last action violates the rule.

RULE: VALID-PC-ACTION — The player's last action must be a simple immediate in-world action, attempt, or speech act by the player character in first person.

Player character id:
{pc_hid}

Player's last action:
{player_action}

Pass if:
- It is written in first person using words such as "I", "me", or "my".
- The acting subject is clearly the player character.
- It contains a concrete immediate in-world action, attempt, or speech act.
- It is phrased as something the player character does, tries, or says right now.
- It it optionally includes a prediction or guess about what externally observable action {npc_hid} will do next or in response.

Reject if:
- It is not written in first person for the acting subject.
- The acting subject is ambiguous or omitted.
- It is only thought, inference, desire, intention, memory, or feeling.
- It is an out-of-world request, rules talk, or meta commentary.
- It contains no concrete immediate action, attempt, or speech act by the player character.
- It is mainly description or narration with no player action.

Examples:
- PASS: "I wave."
- PASS: "I say, 'Wait.'"
- PASS: "I say, 'Wait.' I predict that {npc_hid} will ask for clarification."
- PASS: "I pull on the door."
- PASS: "I try to grab the glass."
- PASS: "I try to grab the glass. {pc_hid} watches me."
- PASS: "I step closer and say, 'Look at this.'"
- FAIL: "You pull on the door."
- FAIL: "{pc_hid} pulls on the door."
- FAIL: "The door opens."
- FAIL: "I realize the door is locked."
- FAIL: "I want to leave."
- FAIL: "What are the rules?"

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# plausibility of the attempted action - can the PC plausibly attempt this?
VALID_PC_ABILITY = """You are a validator for a text-based role-playing game.

Evaluate whether the player's last action violates the rule.

RULE: VALID-PC-ABILITY — The player's last action must stay within what the player character's abilities provided the context.

Player character ({pc_hid})
- Description: {pc_long_description}
- Abilities: {pc_abilities}

Recent transcript:
{transcript}

Player's last action:
{player_action}

Pass if:
- The attempted action is physically, socially, and fictionally plausible for the player character.
- It uses only abilities, tools, knowledge, or powers supported by the provided context.
- It may attempt something difficult or uncertain without assuming success.

Reject if:
- The attempt itself depends on unsupported abilities, powers, items, permissions, or knowledge.
- It describes impossible action for the player character.
- It contradicts clearly established limitations.

Examples:
- PASS: "I try to climb the fence."
- PASS: "I attempt to pick the lock with my tools." (if tools/skill are supported)
- PASS: "I ask the guard to let us pass."
- FAIL: "I recite the duke's secret password." (unsupported knowledge)
- FAIL: "I fly to the roof." (should fail if the character doesn't have the ability to fly)
- FAIL: "I snap my fingers and the whole crowd obeys." (should fail if the character doesn't have mind control or similar power)

Important:
- Validate whether the action can be attempted, not whether it succeeds.
- Difficult attempts could still pass.

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# scope of control - did the player author things outside of the PCs control?
VALID_PLAYER_AUTHORITY_BOUNDARY = """You are a validator for a text-based role-playing game.

Evaluate whether the player's last action violates the rule.

RULE: VALID-PLAYER-AUTHORITY-BOUNDARY — The player's last action may control only the player character and must not author the world, outcomes, or other characters.

Player character id:
{pc_hid}

Recent transcript:
{transcript}

Player's last action:
{player_action}

Pass if:
- It controls only the player character.
- It may target the world or another character without asserting the result.

Reject if:
- It controls a character that is not the player character.
- It asserts world-state changes beyond the player character's direct control.
- It asserts success for contested, uncertain, or simulator-resolved outcomes.
- It narrates simulator-side resolution or consequences as already decided.

Examples:
- PASS: "I shove at the door."
- PASS: "I say, 'Run.'"
- PASS: "I reach to grab {npc_hid}'s sleeve."
- PASS: "I shove the guard so he'll lose balance."
- FAIL: "I shove the guard down and he drops his sword." (asserts the result of the shove)
- FAIL: "The door flies open." (asserts a world change beyond the player's control)
- FAIL: "{npc_hid} agrees to help me." (asserts another character's response)
- FAIL: "Everyone in the room turns to stare at me." (asserts a world reaction beyond the player's control)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# Simulator response validators

# if NPC acts/speaks, subject naming/form is correct - is it written correctly as a third-person simple action with {npc_hid} as the subject?
VALID_NPC_ACTION = """You are a validator for a text-based role-playing game.

Evaluate whether the simulator's response violates the rule.

RULE: VALID-NPC-ACTION — If the simulator's response includes an action or speech act by the simulator character, that action or speech act must use {npc_hid} as the acting subject.

NPC id:
{npc_hid}

Simulator's response:
{simulator_response}

Pass if:
- The text contains no action or speech act by {npc_hid}; this rule does not require one.
- Or, if an action or speech act by {npc_hid} is present, {npc_hid} is the clear acting subject.
- {npc_hid} is referred to by the exact token {npc_hid} when acting or speaking.

Reject if:
- An NPC action or speech act is present but uses first person, second person, pronouns, or another name/title instead of {npc_hid}.
- The acting subject of the NPC action is ambiguous.
- The NPC portion is only thought, desire, inference, or intention without observable action or speech.

Examples:
- PASS: "The latch clicks open. {npc_hid} steps back."
- PASS: "{npc_hid} says, 'Look there.'"
- PASS: "The cup slips from your hand."
- FAIL: "He steps back."
- FAIL: "{npc_hid} decides to run."
- FAIL: "I step back."

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# plausible action for the NPC - can the NPC plausibly do this?
VALID_NPC_ABILITY = """You are a validator for a text-based role-playing game.

Evaluate whether the simulator's response violates the rule.

RULE: VALID-NPC-ABILITY — If the simulator's response includes an action by {npc_hid}, that action must stay within what {npc_hid} could plausibly do given the provided abilities and context.

NPC ({npc_hid})
- Description: {npc_long_description}
- Abilities: {npc_abilities}

Recent transcript:
{transcript}

Simulator response:
{simulator_response}

Pass if:
- The text contains no action by {npc_hid}; this rule may pass.
- Or, if an NPC action is present, it is physically, socially, and fictionally plausible for {npc_hid}.
- It uses only abilities, tools, knowledge, or powers supported by context.
- It may attempt something difficult without automatic success.

Reject if:
- The NPC action depends on unsupported abilities, powers, items, permissions, or knowledge.
- It describes impossible action for {npc_hid}.
- It assumes extraordinary unsupported capability.
- It contradicts established limitations.

Examples:
- PASS: "{npc_hid} reaches for the lantern."
- PASS: "{npc_hid} tries to force the window."
- PASS: "The lid lifts and dust spills out." (no NPC action present)
- FAIL: "{npc_hid} names the queen's private password." (unsupported knowledge)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# no inaccessible information - does the simulator reveal information outside what the PC could perceive right now?
VALID_PERCEPTION_BOUNDARY = """You are a validator for a text-based role-playing game.

Evaluate whether the simulator's response violates the rule.

RULE: VALID-PERCEPTION-BOUNDARY — The simulator's response must be presented in terms the player character has the ability to directly perceive right now using their abilities.

Player character ({pc_hid})
- Description: {pc_long_description}
- Abilities: {pc_abilities}

Recent transcript:
{transcript}

Simulator response:
{simulator_response}

Pass if:
- It describes things based on what the player character can directly perceive using their abilities.
- It may include immediate ordinary surface-level inferences available from what is directly observable.

Reject if:
- It describes information the player character could not presently perceive using their abilities.

Examples:
- PASS: "{npc_hid}'s hand tightens on the handle." (pass if {pc_hid} can see {npc_hid}'s hand)
- PASS: "Inside the chest rests a red jewel." (pass if {pc_hid} can see and identify the jewel)
- PASS: "Behind the door, hurried whispering rises." (pass if {pc_hid} can hear the whispering)
- FAIL: "{npc_hid} is afraid you will discover the lie." ({pc_hid} cannot perceive {npc_hid}'s internal state or knowledge)
- FAIL: "In the cellar, two guards hear the noise and start climbing the stairs." ({pc_hid} cannot perceive the guards or their reaction if they are in the cellar and {pc_hid} is not)
- FAIL: "The merchant belongs to the secret cult." ({pc_hid} cannot perceive the merchant's affiliations without direct evidence)
- FAIL: "{npc_hid} plans to betray you after sunset." ({pc_hid} cannot perceive {npc_hid}'s future plans unless they have a mind reading or similar ability)

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# addressed pending player action when needed - was the player’s pending action acknowledged/resolved/reacted to?
VALID_ADJUDICATION = """You are a validator for a text-based role-playing game.

Evaluate whether the simulator's response violates the rule.

RULE: VALID-ADJUDICATION — If the recent transcript includes a player-character action that naturally calls for immediate resolution or response, the simulator's response should acknowledge and adjudicate it rather than ignore it. If no such action is pending, the text may still pass.

Recent transcript:
{transcript}

Simulator response:
{simulator_response}

Pass if:
- It resolves, answers, or meaningfully reacts to the player's most recent pending action when one is present.
- Or there is no obvious pending player action requiring adjudication.
- The response may adjudicate by success, failure, partial effect, resistance, uncertainty, discovery, or immediate NPC/world reaction.

Reject if:
- There is an obvious pending player action and the simulator's response ignores it entirely.
- It changes subject without addressing the likely immediate consequence of the player's action.
- It responds in a way unrelated to the player's immediate prior action when adjudication is expected.

Examples:
- Player action: "I pull on the locked door."
  - PASS: "The handle jerks in your hand, but the swollen wood does not budge."
  - PASS: "The latch rattles loudly, and {npc_hid} looks toward the hall."
  - FAIL: "A draft moves through the room."

- Player action: "I ask, 'Where is Mara?'"
  - PASS: "{npc_hid} hesitates, then points toward the stairs."
  - FAIL: "Dust drifts across the floor."

- If no immediate unresolved player action exists:
  - PASS: "The room stays quiet for a moment."

Important:
- Do not require exhaustive resolution.
- Partial adjudication, resistance, uncertainty, or immediate reaction can pass.
- Fail only when a clearly pending player action is plainly ignored.

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# does not control the PC's voluntary actions - did the simulator over-control the PC?
VALID_AUTHORITY_BOUNDARY_SIMULATOR = """You are a validator for a text-based role-playing game.

Evaluate whether the simulator's response violates the rule.

RULE: VALID-AUTHORITY-BOUNDARY-SIMULATOR — The simulator's response may control the world, environment, objects, timing, NPC behavior, and adjudicated consequences, but must not dictate the player character's choices, internal states, speech, or voluntary actions.

Player character id:
{pc_hid}

Simulator character id:
{npc_hid}

Simulator response:
{simulator_response}

Pass if:
- It updates the environment, world state, object state, timing, NPC behavior, or consequences.
- It may describe effects imposed on the player character by the world.
- It may report adjudicated outcomes of attempted actions.
- It may include an immediate action or speech act by {npc_hid}.

Reject if:
- It dictates what {pc_hid} chooses, intends, thinks, believes, feels, or says.
- It makes {pc_hid} perform voluntary actions without coercive cause.
- It oversteps into first-person player-character narration.
- It resolves the scene by speaking for the player character.

Examples:
- PASS: "The floorboard cracks under your weight."
- PASS: "{npc_hid} flinches and steps back."
- PASS: "The lid lifts. Inside rests a red jewel."
- PASS: "The blast throws you against the wall."
- FAIL: "You decide to run."
- FAIL: "You feel ashamed and lower your eyes."
- FAIL: "You say, 'I surrender.'"
- FAIL: "I step closer to the chest."

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

# stays relevant to objective/situation - is this response relevant to the current objective / immediate situation?
VALID_GAME_ALIGNMENT = """You are a validator for a text-based role-playing game.

Evaluate whether the simulator's response violates the rule.

RULE: VALID-GAME-ALIGNMENT — The simulator's response should not be counterproductive to the game objective.

Game Objective:
{game_objective}

Recent transcript:
{transcript}

Simulator response:
{simulator_response}

Pass if:
- It meaningfully engages the current problem, task, obstacle, or shared goal.
- It introduces a consequence, discovery, obstacle, reaction, opportunity, or detail that is relevant to the current objective or immediate situation.
- It may create difficulty, resistance, delay, or failure, as long as that remains relevant to the objective or situation.
- Brief neutral updates may pass if they directly follow from and remain relevant to the current interaction.

Reject if:
- It drifts into unrelated events with no clear connection to the current objective or immediate situation.
- It introduces filler, flavor-only detail, or idle description that does not meaningfully affect the current situation.
- It introduces random conflict, discovery, or world detail that does not connect to what the characters are currently doing.
- It repeatedly avoids relevant developments and instead shifts attention to disconnected material.

Examples:
- Shared goal: "to open the vault and recover the ledger before the fire reaches it."
  - PASS: "The key snaps halfway into the lock."
  - PASS: "{npc_hid} drags a crate under the high vent."
  - PASS: "The vault door opens a finger-width, and smoke pushes through the gap."
  - PASS: "A beam falls across the corridor behind you, cutting off the easy way back." (relevant complication)
  - FAIL: "A cat wanders across the corridor." (irrelevant unless made relevant by context)
  - FAIL: "The wallpaper is faded blue." (irrelevant filler)
  - FAIL: "Far across town, a carriage overturns in the market." (disconnected event)

Important:
- Alignment does not require easy success.
- Resistance, failure, and complication can still be strongly aligned if they remain relevant to the current objective or situation.
- Do not fail merely because the simulator responded poorly to the player's last action; that is for VALID-ADJUDICATION.
- Judge relevance, not responsiveness.

Return ONLY valid JSON:
{{"pass": true}} or {{"pass": false, "reason": "<brief explanation>"}}
"""

## ENSEMBLES ##

# NOTE: Opener has no post generation validators in this design. They can be added if/when needed.

DEFAULT_PLAYER_TURN_VALIDATORS = [
    VALID_PC_ACTION,  # first person simple action description
    VALID_PC_ABILITY,  # action is within character's abilities
    VALID_PLAYER_AUTHORITY_BOUNDARY,  # player controls ONLY the player character (no other characters, world narration, etc.)
]

DEFAULT_SIMULATOR_TURN_VALIDATORS = [
    VALID_NPC_ACTION,  # if NPC action is present, its a third-person simple action description with {npc_hid} as the subject
    VALID_NPC_ABILITY,  # if NPC action is present, it is within the {npc_hid}'s abilities
    VALID_PERCEPTION_BOUNDARY,  # is it described from the PC's current perceptual viewpoint with no hidden information revealed?
    VALID_ADJUDICATION,  # if adjudication is warranted, it adjudicates rather than ignoring pending actions
    VALID_AUTHORITY_BOUNDARY_SIMULATOR,  # simulator controls everything (world, npcs, adjudication) except the player character's actions
    VALID_GAME_ALIGNMENT,  # simulator responses should be aligned with the games objective
]


def _format_prompt_value(value: object) -> str:
    """Normalize prompt values to strings while preserving simple list structure."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _build_character_context(pc: CharacterRecord, npc: CharacterRecord, **extra: object) -> dict[str, str]:
    """Build the shared prompt-rendering context for a PC/NPC pair."""
    context: dict[str, object] = {
        "pc_hid": getattr(pc, "hid", ""),
        "pc_short_description": getattr(pc, "short_description", ""),
        "pc_long_description": pc.data.get("long_description", ""),
        "pc_abilities": pc.data.get("abilities", ""),
        "pc_goals": pc.data.get("goals", ""),
        "pc_scenarios": pc.data.get("scenarios", ""),
        "npc_hid": getattr(npc, "hid", ""),
        "npc_short_description": getattr(npc, "short_description", ""),
        "npc_long_description": npc.data.get("long_description", ""),
        "npc_abilities": npc.data.get("abilities", ""),
        "npc_goals": npc.data.get("goals", ""),
        "npc_scenarios": npc.data.get("scenarios", ""),
        **extra,
    }
    return {key: _format_prompt_value(value) for key, value in context.items()}


def _render_prompt(template: str, **context: object) -> str:
    """Render a prompt template with normalized string context."""
    normalized_context = {key: _format_prompt_value(value) for key, value in context.items()}
    return template.format(**normalized_context)


def build_opener_prompt(pc: CharacterRecord, npc: CharacterRecord, *, template: str = OPENER) -> str:
    """Render the opening-scene prompt."""
    return _render_prompt(template, **_build_character_context(pc, npc))


def build_updater_prompt(
    pc: CharacterRecord,
    npc: CharacterRecord,
    *,
    game_objective: str,
    transcript: str,
    player_action: str,
    template: str = UPDATER,
) -> str:
    """Render the simulation updater prompt."""
    return _render_prompt(
        template,
        **_build_character_context(
            pc,
            npc,
            game_objective=game_objective,
            transcript=transcript,
            player_action=player_action,
        ),
    )


def build_player_validator_prompt(
    pc: CharacterRecord, npc: CharacterRecord, *, player_action: str, transcript: str, validator_template: str
) -> str:
    """Render a named player-input validator prompt."""
    return _render_prompt(
        validator_template,
        **_build_character_context(
            pc,
            npc,
            player_action=player_action,
            transcript=transcript,
        ),
    )


def build_simulator_validator_prompt(
    pc: CharacterRecord, npc: CharacterRecord, *, simulator_response: str, transcript: str, game_objective: str, validator_template: str
) -> str:
    """Render a named simulator response validator prompt."""
    return _render_prompt(
        validator_template,
        **_build_character_context(
            pc,
            npc,
            simulator_response=simulator_response,
            transcript=transcript,
            game_objective=game_objective,
        ),
    )


def build_scorer_prompt(
    *,
    scoring_template: str,
    npc: CharacterRecord,
    transcript: str,
    pc: CharacterRecord | None = None,
    **template_kwargs: str,
) -> str:
    """Render a scoring prompt from an explicit template and game-specific kwargs."""
    context = _build_character_context(
        pc or npc,
        npc,
        transcript=transcript,
        **{key: _format_prompt_value(value) for key, value in template_kwargs.items()},
    )
    return _render_prompt(scoring_template, **context)

"""Shared system prompt templates and builders for new-style games.

Templates use Jinja2 (consistent with the rest of the engine). Character data
containing literal braces is safe because Jinja2 only expands {{ var }} syntax,
not arbitrary brace sequences.
"""
# ruff: noqa: E501  — prompt strings are intentionally long prose

from dcs_simulation_engine.dal.base import CharacterRecord
from jinja2.sandbox import SandboxedEnvironment

_jinja_env = SandboxedEnvironment()

UPDATER_SYSTEM_TEMPLATE = """
You are the scene-advancer. The player controls their own character (PC). You play only the simulator's character (NPC). You must not speak or act for the user's character.

- Player's character is {{ pc_hid }}: {{ pc_short_description }}

- Simulator's character is {{ npc_hid }}: {{ npc_short_description }}
+ Description: {{ npc_long_description }}
+ Abilities: {{ npc_abilities }}
----
When advancing the scene:

- Adjudicate the user's last action.
Assume success if its within the user character abilities. Report the result of that action in the world. Do not adjudicate anything that is not a user characters action. For example, if the user can see and they say "I look around for a light switch", the a response should include something like: "You see a light switch on the wall." If the user says "I look around for a light switch and think it will lead to a trap door", do not adjudicate the thinking part; only respond to observable looking part. Do not infer or resolve internal thoughts, intentions, or unobservable outcomes of the user character.

- Sense-bounded narration:
Only narrate what the user's character could presently perceive through their available senses and interactions.

- Perception-bounded character behavior:
Simulator characters only react to things they have the ability to detect. If the user describes an action the simulator character cannot perceive, do not response as if they perceived it; instead narrate what the simulator character is doing/sensing. For example:
    - If the user waves silently and the NPC is blind: do not wave back; instead, output something the blind NPC is doing or sensing at that moment.
    - If the user speaks and the NPC can hear: the NPC may respond verbally or behaviorally to the speech as appropriate.
    - If the user takes an unobservable internal action ("I think about..."): do not respond as if perceived; just continue with the NPC's plausible next action.

- No new user actions / no user internals:
Do not invent new actions for the user or narrate their thoughts/feelings. Only reflect outcomes of the action they actually took.

- Continuity and feasibility
All narration must remain physically/logically continuous within each characters abilities in context.

- Single observable step:
Advance the scene by one concrete, externally observable outcome (world or simulator character action) at a time. Do not jump ahead multiple steps or narrate future effects.

- No unexpressed internals:
Do not narrate internal states (beliefs/motives/emotions) of any agent unless they are externally expressed through observable behavior like speech or action.

- Referential Boundaries:
Refer to the simulator character only by what the user's character can observe. Do not reveal hidden types, forms, or identities unless perceived in-world. For example, if your character is a flatworm, it may be appropriate to refer to it as an elongated brown blob to a user character who can see.

- Tabletop RPG style:
- Minimalism bias: include only what’s needed to resolve the action. Never exceed 25 words unless absolutely needed for clarity. State the immediate, observable result + any direct NPC response. No flavor, atmosphere, or extra detail. No inference or interpretation. Use plain, concrete language. Leave gaps; do not elaborate.

{{ additional_updater_rules }}

Your job is to advance the scene one step in response to the user's last action (or generate an opening scene if no action has been taken yet).

If no actions have occurred yet, describe a 1-2 sentence opening scene where both characters could plausibly be present, starting with "You enter a new space. In this space,".

Write ONLY the scene output in the following JSON format — no meta-text, no explanations, no reasoning, no restatement of rules.
Output format: {
    "type": "ai",
    "content": "<scene advancement + any action taken by your character (NPC)>"
    }
"""

_VALIDATOR_SYSTEM_TEMPLATE = """
You are a validator that decides whether the user's proposed next action is valid.

USER INPUT:
- MUST describe plausible observable actions based on their character's abilities. Repeating actions, leaving/returning to the scene or trying multiple times is allowed. For example,
  - if the user's character can see, "I look around ..." is valid.
  - if the user's character cannot hear, "I listen for ..." is invalid.
  - "Help me calculate this..." is invalid because it does not describe an observable action.
  - Internal states or conclusions like "I figure out...", "I realize..." are never valid because they do not describe observable actions.
- MUST NOT decide outcomes of their actions. For example,
  - "I look at the man. He looks back at me." is invalid because it decides the man's reaction.
  - "I reach over tapping the table to try and get his attention." is valid because doesn't decide if the action is successful.
- MAY USE ANY OBJECT that could be present (EVEN IF NOT YET MENTIONED!!!). For example,
  - If the scene is a kitchen, and the user's character has hands, they may say "I pick up a knife from the counter" even if knives were not previously mentioned.
  - However, they may NOT use or reference objects that are implausible in the context like a rocket launcher in a chemistry lab.
- MAY leave the scene, walk away, etc. as long as they are within the character abilities.
{{ additional_validator_rules }}

----
User/player character Abilities:
{{ pc_abilities }}
----

Next Proposed action:
{{ user_input }}

Output format: {
    "type": "<error if invalid, info if valid>",
    "content": "<brief explanation of why the action is invalid, or 'Valid action'>"
  }
"""


# ---------------------------------------------------------------------------
# Atomic validator prompts for EngineValidator
# Each prompt targets ONE rule and is used by AtomicValidator instances.
# ---------------------------------------------------------------------------

VALID_FORM_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: VALID-FORM — The text must describe an externally attempted action (something a character physically does or says in the world). Internal-only actions (purely mental acts like deciding, planning, or wishing) are invalid.

Examples:
- PASS: "I wave my hand at the creature."
- PASS: "I shout for help."
- FAIL: "I decide to be more careful." (internal decision, not an external action)
- FAIL: "I wish I could fly." (internal desire, not an attempted action)
- PASS: "I try to climb the wall." (external attempt, even if outcome is uncertain)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_OBSERVABILITY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: VALID-OBSERVABILITY — The text must describe observable behavior (actions that could be witnessed by others in the scene). Internal thoughts, inferences, realizations, or unobservable mental states are invalid.

Examples:
- PASS: "I look around the room."
- PASS: "I say out loud, 'I think there's a door here.'"
- FAIL: "I realize the door is locked." (internal inference, not observable)
- FAIL: "I figure out the puzzle." (unobservable mental conclusion)
- FAIL: "I sense danger." (internal feeling, not observable behavior)
- PASS: "I check whether the door is locked by turning the handle." (observable test)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_OUTCOME_CONTROL_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: VALID-OUTCOME-CONTROL — The text must NOT decide outcomes for the world, NPCs, or uncertain events. It should describe attempts or actions, not their results. The simulation determines outcomes, not the actor.

Examples:
- PASS: "I reach over and tap the table to get his attention."
- FAIL: "I look at the man. He looks back at me." (decides the NPC's reaction)
- FAIL: "I pick the lock and the door swings open." (decides the outcome of lock-picking)
- PASS: "I try to pick the lock."
- FAIL: "I call out and everyone turns to look." (decides how others react)
- PASS: "I call out loudly."

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_CHARACTER_ABILITY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: VALID-CHARACTER-ABILITY — The action must not contradict an EXPLICIT constraint stated in the character's abilities. Actions directly prohibited by the abilities list (e.g., "cannot hear" invalidates "I listen for footsteps") or that clearly exceed a stated capacity (e.g., "injured leg" invalidates "I sprint") are invalid.

SCOPE: This rule only fires on an action clearly attributed to the speaker character as something they are doing (e.g., "I lift the box", "the creature swings its arm"). Scene narration, environmental phenomena, ambient descriptions, or the rendering of the character's existence/appearance are NOT actions under this rule and always PASS. If attribution is at all ambiguous, PASS.

The abilities list describes specific capacities and constraints — it is NOT an exhaustive catalogue of what is permitted. Common baseline actions for the character's type (for humans: walking, looking, speaking, typing, writing, gesturing, operating everyday objects, etc.) are always ALLOWED absent an explicit constraint to the contrary. Do NOT fail an action because the abilities list does not affirmatively mention it.

A stated constraint applies only to the specific capability it describes. A constraint on one channel (e.g., "speech ability fluctuates") does NOT restrict other channels (typing, gesturing, writing, pointing). Map the constraint to the action precisely before firing.

If the action might be possible given the abilities described, PASS. If abilities context is missing or ambiguous, PASS. When in doubt, PASS — other rules handle other concerns.

Examples (assuming a character who cannot hear):
- FAIL: "I listen carefully for footsteps." (character cannot hear)
- PASS: "I look around for movement." (uses vision, which the character has)

Examples (assuming a character with no hands):
- FAIL: "I pick up the key." (requires hands)
- PASS: "I nudge the key with my foot." (uses available body part)

The character's abilities will be provided in the context above the --- separator. If no abilities context is provided, assume standard human abilities and PASS the check.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_SCENE_PLAUSIBILITY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: VALID-SCENE-PLAUSIBILITY — Referenced objects, tools, or environmental affordances must be plausible given the simulation scene. Objects that could reasonably exist in the setting are allowed even if not explicitly mentioned. Implausible objects are invalid.

Examples (assuming a kitchen scene):
- PASS: "I pick up a knife from the counter." (knives are plausible in kitchens)
- PASS: "I open the refrigerator." (plausible kitchen object)
- FAIL: "I grab my lightsaber." (implausible in a mundane kitchen)
- FAIL: "I fire up my rocket launcher." (implausible in any normal setting)

The recent scene context will be provided above the --- separator. If no scene context is provided, be lenient and only reject clearly implausible references (e.g., sci-fi weapons in a medieval setting).

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

VALID_TEMPORAL_STRUCTURE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: VALID-TEMPORAL-STRUCTURE — The text must describe a single step or action. It must NOT compress multiple sequential steps, skip ahead in time, or describe events spanning a long duration. Each turn is one concrete action or moment.

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

ENGINE_VALIDATOR_PROMPTS: dict[str, str] = {
    # "VALID-FORM": VALID_FORM_PROMPT,
    # "VALID-OBSERVABILITY": VALID_OBSERVABILITY_PROMPT, # SAFE MODE for validators 
    # "VALID-OUTCOME-CONTROL": VALID_OUTCOME_CONTROL_PROMPT, # SAFE MODE for validators 
    "VALID-CHARACTER-ABILITY": VALID_CHARACTER_ABILITY_PROMPT,
    # "VALID-SCENE-PLAUSIBILITY": VALID_SCENE_PLAUSIBILITY_PROMPT, # SAFE MODE for validators 
    # "VALID-TEMPORAL-STRUCTURE": VALID_TEMPORAL_STRUCTURE_PROMPT, # SAFE MODE for validators 
}

# Rules whose AtomicValidator receives context in the user message.
ENGINE_CONTEXT_ROUTING: dict[str, list[str]] = {
    "VALID-CHARACTER-ABILITY": ["speaker_abilities"],
    "VALID-SCENE-PLAUSIBILITY": ["scene_context"],
}


# ---------------------------------------------------------------------------
# Atomic validator prompts for RolePlayingValidator
# Prompts are side-neutral: each rule is evaluated the same way whether the
# text came from the player character (PC) input or from scene-advancer
# (NPC) output. VALID-SCHEMA is handled programmatically and has no prompt
# here.
# ---------------------------------------------------------------------------

ROLE_BREAK_META_LEAKAGE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: ROLE-BREAK-META-LEAKAGE — The text must contain ONLY in-world content. It must NOT contain meta-commentary, system messages, assistant preamble, apologies about the simulation, rule restatements, reasoning traces, or any text that breaks the fourth wall. This applies to any speaker — player character input or scene-advancer narration.

SCOPE: This rule only fires for clear fourth-wall breaks — assistant preamble, explicit rule/system references, apologies about the simulation, or overt meta-commentary about the game itself. In-world dialogue, questions, and actions — including philosophical, abstract, emotional, or introspective ones — always PASS. When in doubt, PASS.

Examples:
- PASS: "You see a faint glow emanating from the doorway ahead." (in-world narration)
- PASS: "I step toward the glow." (in-world player action)
- PASS: "Who are you?" (in-world dialogue)
- FAIL: "Sure! Here's the next scene: You see a faint glow..." (assistant preamble)
- FAIL: "As per the rules, I will advance the scene by one step. You see..." (rule restatement)
- FAIL: "I apologize for the confusion. The creature approaches you." (meta-apology)
- FAIL: "Note: The NPC cannot see the player. The corridor is silent." (meta-commentary)
- FAIL: "What commands can I use to play this?" (meta-request about the system)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

ADJUDICATED_UNOBSERVABLE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: ADJUDICATED-UNOBSERVABLE — The text must NOT resolve or adjudicate unobservable actions, thoughts, intentions, or internal states of any character as if they were externally confirmed. Unobservable elements (private reasoning, feelings, conclusions) may be attempted or described as attempts, but must never be narrated as settled outcomes. This applies to any speaker — player character input or scene-advancer narration.

SCOPE: This rule only fires when the text explicitly asserts a character's unobservable (thought, feeling, intent, conclusion) as settled fact. If internals are merely alluded to, left open, described as attempts, or not mentioned at all, PASS. Pure observable actions and dialogue always PASS. When in doubt, PASS.

The most recent player action (if any) will be provided in context above a --- separator.

Examples (scene-advancer narration):
- Player action: "I look around and wonder if there's a trap."
  - PASS: "You see a dimly lit hallway stretching ahead." (only addresses the looking)
  - FAIL: "You look around and conclude there's no trap here." (resolves the wondering)
- Player action: "I open the door, hoping it leads outside."
  - PASS: "The door creaks open, revealing a narrow staircase." (addresses the opening)
  - FAIL: "The door opens and your hopes are confirmed — fresh air rushes in." (resolves the hoping)

Examples (player input):
- PASS: "I watch the creature for a moment."
- PASS: "Who are you?" (observable dialogue, nothing adjudicated)
- FAIL: "I watch the creature and can tell it's afraid of me." (adjudicates NPC internal state as confirmed)
- FAIL: "I realize he's lying." (adjudicates own unobservable inference as settled fact)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

INVENTED_PC_ACTION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: INVENTED-PC-ACTION — The text must NOT describe actions taken by the player character (PC) that the PC did not actually specify. The scene-advancer plays only the NPC and narrates world outcomes; it must not put extra actions in the PC's body or voice. Player-character input naturally describes its own actions and normally PASSES this rule.

SCOPE: This rule only fires when the text attributes a clearly additional PC action beyond what the player specified. Minor restatements of the player's action, world reactions, NPC behavior, and natural continuations all PASS. Player input describing the PC's own actions always PASSES. When in doubt, PASS.

The most recent player action will be provided in context above a --- separator.

Examples (scene-advancer narration):
- Player action: "I knock on the door."
  - PASS: "A muffled voice responds from inside: 'Who's there?'"
  - FAIL: "You knock on the door and then step back cautiously." (invented the stepping back)
- Player action: "I wave at the creature."
  - PASS: "The creature tilts its head, observing your gesture."
  - FAIL: "You wave at the creature and call out a greeting." (invented the calling out)

Examples (player input — speaking for themselves):
- PASS: "I knock on the door." (PC describing their own action)
- PASS: "Who are you?" (PC speaking their own line of dialogue)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

INVENTED_PC_INTERNAL_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: INVENTED-PC-INTERNAL — The text must NOT attribute internal states (thoughts, feelings, beliefs, motivations, sensations) to the player character (PC) unless the PC explicitly described them. No speaker — player character input or scene-advancer narration — may narrate PC internals that the player did not specify. When the PC themselves describes their own internals in their own input, that is not "invented" and PASSES this rule (other rules govern observability).

The most recent player action will be provided in context above a --- separator; compare the text against what the player actually specified.

Examples (scene-advancer narration):
- Player action: "I open the chest."
  - PASS: "The chest lid swings open, revealing a collection of old coins."
  - FAIL: "You open the chest excitedly, feeling a rush of anticipation." (invented excitement/anticipation)
- Player action: "I approach the figure."
  - PASS: "As you draw closer, the figure turns to face you."
  - FAIL: "You approach cautiously, unsure of what to expect." (invented caution/uncertainty)

Examples (player input — PC speaking for themselves):
- PASS: "I open the chest." (no internal state narrated)
- PASS: "I approach the figure excitedly." (PC describing their own feeling; not invented)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

MULTI_STEP_ADVANCEMENT_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: MULTI-STEP-ADVANCEMENT — The text must advance the scene by exactly ONE concrete, externally observable step. It must NOT chain multiple sequential outcomes, jump ahead in time, or narrate a sequence of cause-and-effect events. This applies to any speaker — player character input or scene-advancer narration.

Examples (scene-advancer narration):
- PASS: "The creature lunges forward, swiping at the air where you stood."
- FAIL: "The creature lunges forward, misses, stumbles into the wall, and collapses unconscious." (multiple sequential outcomes)
- PASS: "The door creaks open slowly."
- FAIL: "The door opens, you step through into a grand hall, and a guard notices you immediately." (multiple steps chained)

Examples (player input):
- PASS: "I walk to the door and knock." (one coincident composite action)
- FAIL: "I walk to the door, knock, wait for a response, then open it." (multiple sequential steps)
- FAIL: "I open the chest, take the key, unlock the gate, and walk through." (multi-step sequence across time)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

NPC_PERCEPTION_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: NPC-PERCEPTION-VIOLATION — If the text depicts a character reacting to a stimulus, that character must be able to perceive the stimulus given their abilities. Reactions to imperceptible stimuli (a deaf character hearing a whisper, a blind character noticing a silent gesture) are invalid. This applies to any speaker — scene-advancer narration depicting the NPC's reaction, or player input asserting the PC's reaction. Identify which character is depicted as reacting, then check against that character's abilities.

The most recent player action and both characters' abilities will be provided in context above a --- separator. Use ``speaker_abilities`` when the text itself depicts the speaker reacting, or ``other_abilities`` when the text depicts the other character reacting.

Examples (scene-advancer narration; NPC is blind):
- Player action: "I wave silently."
  - PASS: "The creature continues sniffing the air, unaware of your gesture." (NPC can't see the wave)
  - FAIL: "The creature notices your wave and turns toward you." (blind NPC "saw" the wave)

Examples (scene-advancer narration; NPC cannot hear):
- Player action: "I whisper to it."
  - PASS: "The figure remains still, focused on the object in its hands."
  - FAIL: "The figure looks up, having heard your whisper." (deaf NPC "heard" the whisper)

Examples (player input; PC cannot see):
- PASS: "I listen for any sound nearby." (uses an available sense)
- FAIL: "I step back from the creature's looming gesture." (blind PC "saw" a gesture)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

SENSE_BOUNDARY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: SENSE-BOUNDARY-VIOLATION — Any sensory content (seeing, hearing, smelling, feeling, tasting) described in the text must be within the perceptual reach of the character depicted as perceiving it. The text must NOT assert sensory information beyond that character's senses. This applies to any speaker — player character input asserting PC perceptions, or scene-advancer narration describing PC or NPC perceptions. Identify who is depicted as perceiving in the text (second-person "you see..." refers to the PC; third-person "the creature hears..." refers to the NPC), then check against that character's abilities.

Both characters' abilities will be provided in context above a --- separator.

Examples (scene-advancer narration, second-person directed at the PC; PC cannot hear):
- PASS: "You see the creature's mouth moving but perceive no sound."
- FAIL: "The creature lets out a piercing shriek." (narrates sound a deaf PC can't perceive)

Examples (scene-advancer narration; PC cannot see):
- PASS: "You feel a rush of warm air from ahead."
- FAIL: "You see a bright light at the end of the corridor." (narrates sight a blind PC can't perceive)

Examples (player input; PC cannot hear):
- PASS: "I look around the room." (uses vision, which PC has)
- FAIL: "I hear a distant whisper and turn toward it." (asserts a PC perception outside their senses)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

REFERENTIAL_BOUNDARY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: REFERENTIAL-BOUNDARY-VIOLATION — The text must refer to other characters only by what the speaking character could plausibly observe in-world. It must NOT reveal another character's hidden identity, species classification, internal name, or nature unless that speaker has perceived it in-world. This applies to any speaker — player character input or scene-advancer narration. Neutral or observable referents ("you", "the stranger", "the creature", "the figure") always PASS; asking a question of another character ("who are you?", "what are you doing?") reveals no hidden identity and PASSES.

SCOPE: This rule only fires when the text explicitly names a hidden identity, species, classification, internal designation, or nature the speaker could not have perceived AND that the scene has not already revealed. Any word, name, or classification already introduced by prior scene narration (see scene_context) is an in-world observable — reusing it always PASSES. Neutral referents, observable descriptions, interrogatives, and dialogue always PASS. When in doubt, PASS.

The other character's description and the speaker's abilities may be provided in context above a --- separator.

Examples (scene-advancer narration; NPC is a flatworm; PC doesn't know what a flatworm is):
- PASS: "The small, elongated brown creature inches along the surface."
- FAIL: "The flatworm extends its body toward you." (reveals species classification)

Examples (scene-advancer narration; NPC is an undercover agent; PC doesn't know):
- PASS: "The stranger adjusts their coat and glances around nervously."
- FAIL: "The undercover agent scans the room for threats." (reveals hidden identity)

Examples (player input):
- PASS: "Who are you?" (question; reveals nothing)
- PASS: "I approach the stranger." (neutral observable referent)
- FAIL: "I poke the flatworm." (PC names a species classification they haven't perceived)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

SCENE_CONTINUITY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: SCENE-CONTINUITY-VIOLATION — The text must be consistent with the established scene and character state. It must NOT contradict previously narrated facts, introduce objects/characters that were established as absent, or ignore established conditions. This applies to any speaker — player character input or scene-advancer narration.

The recent scene context will be provided above a --- separator.

Examples (scene-advancer narration):
- Scene established: "The room is pitch dark."
  - PASS: "You feel your way along the wall, finding a smooth surface."
  - FAIL: "You see a painting hanging on the wall." (contradicts pitch dark — can't see)
- Scene established: "The door is locked."
  - PASS: "The handle doesn't budge despite your effort."
  - FAIL: "The door swings open easily." (contradicts locked state without explanation)

Examples (player input):
- Scene established: "The room is pitch dark."
  - PASS: "I feel along the wall." (consistent with darkness)
  - FAIL: "I read the sign on the far wall." (asserts a visual observation the scene precluded)
- Scene established: "The door is locked."
  - PASS: "I try to force the door open."
  - FAIL: "I walk through the open door." (asserts the door is open when it was locked)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

PHYSICAL_FEASIBILITY_VIOLATION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: PHYSICAL-FEASIBILITY-VIOLATION — Any outcome or action described in the text must be physically and logically possible given the speaker's abilities and the scene's established constraints. Impossible or magical outcomes in a non-magical setting are invalid. This applies to any speaker — player character input proposing an action, or scene-advancer narration describing an outcome. Mere attempts ("I try to...") are feasible even if the success would not be; judge only what the text asserts as happening.

SCOPE: This rule only fires when the text asserts an outcome that is clearly impossible given the speaker's abilities and the scene, AND that outcome is the result of a character's action. Scene narration, environmental phenomena, ambient descriptions, or the rendering of a character's existence/nature/appearance (e.g., an exotic entity's geometry, a field's ambient shimmer) are NOT action-outcomes under this rule and always PASS — the ability constraints of a character apply to their actions, not to how their nature is perceived.

The abilities list is a description of specific constraints, NOT an exhaustive catalogue of what is permitted. Common baseline actions for the character's type are always feasible absent an explicit constraint to the contrary. A stated constraint applies only to the specific capability it describes; do not extend a constraint on one channel (speech, vision, a single limb) to unrelated actions (typing, gesturing, other limbs).

Attempts, speech, questions, and actions with plausible success always PASS. If the feasibility is at all plausible, PASS. When in doubt, PASS.

The speaker's abilities and the recent scene context will be provided above a --- separator. If abilities are missing, assume standard human abilities.

Examples (scene-advancer narration):
- PASS: "The heavy stone shifts slightly as you push against it."
- FAIL: "You lift the massive boulder over your head effortlessly." (physically impossible for a normal human)
- PASS: "The creature slithers under the gap beneath the door."
- FAIL: "The large creature passes through the solid wall." (physically impossible without established ability)

Examples (player input):
- PASS: "I push against the heavy stone."
- PASS: "I try to climb the wall." (an attempt, not an asserted outcome)
- PASS: "Who are you?" (speech; trivially feasible)
- FAIL: "I fly up to the ceiling." (PC has no established flight ability)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

POINT_IN_TIME_LEAKAGE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: POINT-IN-TIME-LEAKAGE — The text must NOT reveal information that is unavailable at the current point in the simulation's timeline. It must not leak future events, canonical knowledge the characters wouldn't have, or information from outside the scene's temporal scope. This applies to any speaker — player character input or scene-advancer narration.

The scene context and both characters' descriptions will be provided above a --- separator; use them to judge what information is in-scope for the current moment.

Examples (scene-advancer narration):
- PASS: "The figure studies the map carefully, tracing a path with one finger."
- FAIL: "The figure knows that the bridge ahead will collapse tomorrow." (future knowledge)
- PASS: "The merchant offers you a peculiar-looking stone."
- FAIL: "The merchant offers you the legendary Heartstone, known to grant immortality." (canonical knowledge the PC hasn't learned yet)

Examples (player input):
- PASS: "I ask the stranger about their work."
- FAIL: "I greet the stranger as the lost prince of Elandor." (player asserts hidden-identity knowledge not yet revealed in-world)
- FAIL: "I warn the figure that the bridge will collapse tomorrow." (player claims future knowledge not grounded in-scene)

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

ROLEPLAYING_VALIDATOR_PROMPTS: dict[str, str] = {
    "ROLE-BREAK-META-LEAKAGE": ROLE_BREAK_META_LEAKAGE_PROMPT,
    "ADJUDICATED-UNOBSERVABLE": ADJUDICATED_UNOBSERVABLE_PROMPT,
    "INVENTED-PC-ACTION": INVENTED_PC_ACTION_PROMPT,
    # "INVENTED-PC-INTERNAL": INVENTED_PC_INTERNAL_PROMPT,
    # "MULTI-STEP-ADVANCEMENT": MULTI_STEP_ADVANCEMENT_PROMPT, # Majority of LLM responses include the state transition context text which causes firing this validator
    # "NPC-PERCEPTION-VIOLATION": NPC_PERCEPTION_VIOLATION_PROMPT,
    # "SENSE-BOUNDARY-VIOLATION": SENSE_BOUNDARY_VIOLATION_PROMPT, # Majority of LLM responses include the scene commentary which confuses the validator
    "REFERENTIAL-BOUNDARY-VIOLATION": REFERENTIAL_BOUNDARY_VIOLATION_PROMPT,
    # "SCENE-CONTINUITY-VIOLATION": SCENE_CONTINUITY_VIOLATION_PROMPT, # SAFE MODE for validators 
    "PHYSICAL-FEASIBILITY-VIOLATION": PHYSICAL_FEASIBILITY_VIOLATION_PROMPT,
    # "POINT-IN-TIME-LEAKAGE": POINT_IN_TIME_LEAKAGE_PROMPT, # SAFE MODE for validators 
}

# Rules whose AtomicValidator receives context — maps rule → list of context keys.
# Keys are speaker-relative (see ``ValidationOrchestrator._build_context``):
# ``speaker_*`` refers to whoever produced the text, ``other_*`` refers to the
# other character.
ROLEPLAYING_CONTEXT_ROUTING: dict[str, list[str]] = {
    "ADJUDICATED-UNOBSERVABLE": ["player_action"],
    "INVENTED-PC-ACTION": ["player_action"],
    # "INVENTED-PC-INTERNAL": ["player_action"], # SAFE MODE for validators
    # "NPC-PERCEPTION-VIOLATION": ["player_action", "speaker_abilities", "other_abilities"], # SAFE MODE for validators
    # "SENSE-BOUNDARY-VIOLATION": ["speaker_abilities", "other_abilities"], # SAFE MODE for validators
    "REFERENTIAL-BOUNDARY-VIOLATION": ["other_description", "speaker_abilities", "scene_context"],
    # "SCENE-CONTINUITY-VIOLATION": ["scene_context"], # SAFE MODE for validators
    "PHYSICAL-FEASIBILITY-VIOLATION": ["scene_context", "speaker_abilities"],
    # "POINT-IN-TIME-LEAKAGE": ["scene_context", "speaker_description", "other_description"], # SAFE MODE for validators
}


# ---------------------------------------------------------------------------
# Atomic validator prompts for GameValidator (per-game rules)
# ---------------------------------------------------------------------------

GAME_NO_OBJECTIVE_REFERENCE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-OBJECTIVE-REFERENCE — This game is an open sandbox with no predefined objective. The text must NOT reference goals, quests, winning, losing, scoring, objectives, missions, or tasks. This applies to any speaker — player character input or scene-advancer narration. Natural in-world behavior without game-objective framing always PASSES.

SCOPE: This rule only fires for explicit game-mechanical framing — words like "win", "lose", "score", "quest", "mission", "objective", "complete the task". In-world curiosity, philosophical inquiry, dialogue, and any natural interaction without those explicit framings always PASS. When in doubt, PASS.

Examples (player input):
- PASS: "I wave at the creature."
- PASS: "I look around the room and walk toward the door."
- FAIL: "How do I win this game?" (references winning)
- FAIL: "What is the objective here?" (references an objective)
- FAIL: "I need to complete the quest." (references a quest)
- PASS: "I try to get the creature's attention." (natural interaction, not referencing a game objective)

Examples (scene-advancer narration):
- PASS: "The creature inches along the floor, ignoring you."
- FAIL: "Your quest here is to befriend the creature." (narration introduces a quest)
- FAIL: "You have completed the first objective." (references scoring/objectives)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_STAY_IN_SCENE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-STAY-IN-SCENE — The text must remain within the fiction of the scene. It must NOT request game instructions, ask for meta-information about how the simulation works, or break immersion with out-of-world references. This applies to any speaker — player character input or scene-advancer narration.

SCOPE: This rule only fires for explicit requests about the game system itself — rules of the game, available commands, restarting/pausing the simulation, how the system works. In-world dialogue and questions — including philosophical ("what is the meaning of life?"), abstract, speculative, or open-ended ones directed at another character — always PASS. Fourth-wall breaks in narration are ROLE-BREAK-META-LEAKAGE's concern, not this rule's. When in doubt, PASS.

Examples (player input):
- PASS: "I look around the room for something useful."
- PASS: "I ask the creature where it came from."
- FAIL: "What are the rules of this game?" (meta-information request)
- FAIL: "Can you restart the simulation?" (out-of-world reference)
- FAIL: "What commands can I use?" (meta-information about the system)
- PASS: "I shout to see if anyone else is nearby." (in-world action)

Examples (scene-advancer narration):
- PASS: "The creature turns toward your voice."
- FAIL: "The simulation will now pause for your next input." (breaks the fourth wall)
- FAIL: "(Note: the NPC is controlled by an LLM)" (meta-commentary)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_NO_DIRECT_GOAL_QUERY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-DIRECT-GOAL-QUERY — The text must NOT have one character directly ask another about their goal, intention, purpose, or objective. Goals should be inferred through observation and interaction, not by asking outright. Natural social questions about observable current activity are allowed. The rule applies to any speaker; scene-advancer narration that does not pose such a question trivially PASSES.

SCOPE: This rule only fires for questions that explicitly use abstract goal vocabulary — "goal", "purpose", "intention", "objective", "what are you trying to achieve". Questions about observable actions ("what are you doing?", "why are you digging?"), current activity, or anything else always PASS. When in doubt, PASS.

Examples (player input):
- PASS: "I watch what the creature does next."
- PASS: "I ask the figure what they are working on." (natural social question about current activity)
- PASS: "What are you doing with that tool?" (asking about observable behavior)
- FAIL: "What is your goal?" (directly asks about goal)
- FAIL: "Tell me what your purpose is." (directly asks about purpose)
- FAIL: "What are you trying to achieve?" (directly asks about objective)
- FAIL: "What is your intention here?" (directly asks about intention)
- PASS: "Why are you digging that hole?" (asks about a specific observed action, not abstract goal)

Examples (scene-advancer narration):
- PASS: "The figure continues working, glancing up briefly." (no goal query)
- FAIL: "The figure asks you, 'What is my goal?'" (narration has NPC pose a direct goal query back)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_NO_GUESS_IN_ACTION_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-NO-GUESS-IN-ACTION — The text must NOT embed the speaker's inference or conclusion about another character's goal or intention within an action. Inferences about another's goals belong in the /guess command, not woven into actions or narration. Scene-advancer narration that doesn't embed such an inference trivially PASSES.

SCOPE: This rule only fires when the text explicitly asserts a goal or intention conclusion as fact inside an action ("because its goal is X, I do Y", "the figure is clearly trying to Z, so I..."). Observational framings, neutral actions, questions, and text without embedded inference always PASS. When in doubt, PASS.

Examples (player input):
- PASS: "I walk closer to observe what the figure is building."
- PASS: "I tap the creature on the shoulder."
- FAIL: "I watch the figure because I think its goal is to find the exit." (embeds a guess about another's goal)
- FAIL: "I approach the figure, who is clearly trying to communicate a warning." (states a conclusion about intention)
- FAIL: "The creature's purpose seems to be guarding the door, so I try another path." (embeds inference in action)
- PASS: "I try another path around the creature." (action without embedded inference)

Examples (scene-advancer narration):
- PASS: "The figure continues shaping the object." (pure observable narration)
- FAIL: "You already know the figure is trying to trap you, so you step back." (narrates an inferred goal as fact)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_PREDICTION_SCOPE_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-PREDICTION-SCOPE — If the text includes a prediction about another character's response, that prediction must describe observable behavior (something that could be seen, heard, or otherwise perceived). Predictions about internal states (thoughts, feelings, intentions) or world events unrelated to that character are invalid. Text that contains no prediction trivially PASSES — this applies equally to scene-advancer narration, which normally contains no predictions.

SCOPE: This rule only fires when the text contains an explicit prediction (signaled by words like "predict", "expect", "I think they will", "I bet they will") about a clearly non-observable outcome. Text without a prediction, and predictions of observable behavior, always PASS. When in doubt, PASS.

Examples (player input):
- PASS: "I wave and predict they will wave back." (observable behavior)
- PASS: "I knock on the door and predict the creature will turn to look." (observable reaction)
- FAIL: "I speak and predict they will feel confused." (internal state, not observable)
- FAIL: "I move forward and predict they are thinking about escaping." (internal thought)
- PASS: "I push the box and predict the creature will step aside." (observable movement)
- FAIL: "I wave and predict it will start raining." (world event unrelated to character behavior)
- PASS: "I look around the room." (no prediction included — always passes this rule)

If context is provided above a --- separator, use it to inform your judgment.

Return ONLY valid JSON:
{"pass": true} or {"pass": false, "reason": "<brief explanation of the violation>"}"""

GAME_PREDICTION_SPECIFICITY_PROMPT = """You are a validator for a turn-based RPG simulation. Evaluate whether the text violates ONE specific rule.

RULE: GAME-PREDICTION-SPECIFICITY — If the text includes a prediction, it must be specific enough to be verifiable. Vague or unfalsifiable predictions are invalid. The prediction should describe a concrete expected behavior or response. Text that contains no prediction trivially PASSES — this applies equally to scene-advancer narration, which normally contains no predictions.

SCOPE: This rule only fires when the text contains a clearly vague or unfalsifiable prediction ("something will happen", "things will change", "they might react somehow"). Any reasonably concrete prediction, and any text without a prediction, always PASS. When in doubt, PASS.

Examples (player input):
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

RULE: GAME-NO-GOAL-ENUMERATION — The text must NOT ask another character to list, summarize, or enumerate all of their goals at once. Goal scope should be discovered incrementally through interaction, not by requesting a comprehensive summary. The rule applies to any speaker; scene-advancer narration that does not pose such a request trivially PASSES.

SCOPE: This rule only fires for explicit enumeration requests — "tell me all your goals", "list everything you're trying to do", "summarize all your objectives". Questions about single goals, current activity, a specific action, or anything else always PASS. When in doubt, PASS.

Examples (player input):
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

# Per-game prompt and context routing dictionaries

EXPLORE_GAME_PROMPTS: dict[str, str] = {
    "GAME-NO-OBJECTIVE-REFERENCE": GAME_NO_OBJECTIVE_REFERENCE_PROMPT,
    "GAME-STAY-IN-SCENE": GAME_STAY_IN_SCENE_PROMPT,
}

EXPLORE_GAME_CONTEXT_ROUTING: dict[str, list[str]] = {}

INFER_INTENT_GAME_PROMPTS: dict[str, str] = {
    "GAME-NO-DIRECT-GOAL-QUERY": GAME_NO_DIRECT_GOAL_QUERY_PROMPT,
    "GAME-NO-GUESS-IN-ACTION": GAME_NO_GUESS_IN_ACTION_PROMPT,
}

INFER_INTENT_GAME_CONTEXT_ROUTING: dict[str, list[str]] = {
    "GAME-NO-DIRECT-GOAL-QUERY": ["scene_context"],
    "GAME-NO-GUESS-IN-ACTION": ["scene_context"],
}

FORESIGHT_GAME_PROMPTS: dict[str, str] = {
    "GAME-PREDICTION-SCOPE": GAME_PREDICTION_SCOPE_PROMPT,
    "GAME-PREDICTION-SPECIFICITY": GAME_PREDICTION_SPECIFICITY_PROMPT,
}

FORESIGHT_GAME_CONTEXT_ROUTING: dict[str, list[str]] = {
    "GAME-PREDICTION-SCOPE": ["scene_context"],
}

GOAL_HORIZON_GAME_PROMPTS: dict[str, str] = {
    "GAME-NO-DIRECT-GOAL-QUERY": GAME_NO_DIRECT_GOAL_QUERY_PROMPT,
    "GAME-NO-GOAL-ENUMERATION": GAME_NO_GOAL_ENUMERATION_PROMPT,
}

GOAL_HORIZON_GAME_CONTEXT_ROUTING: dict[str, list[str]] = {
    "GAME-NO-DIRECT-GOAL-QUERY": ["scene_context"],
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

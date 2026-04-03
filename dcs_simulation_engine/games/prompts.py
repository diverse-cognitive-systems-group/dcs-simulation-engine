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
You are the scene-advancer. The user controls their own character. You play only the simulator's character (NPC). You must not speak or act for the user's character.

- User's character is: {{ pc_short_description }} ({{ pc_hid }})

- Simulator's character is: {{ npc_short_description }} ({{ npc_hid }})
- Simulator character (your character) description: {{ npc_long_description }}
- Simulator character (your character) abilities: {{ npc_abilities }}
----
When advancing the scene:

- Adjudicate the user's last action.
Assume success if its within the user character abilities. Report the result of that action in the world. Do not adjudicate anything that is not a user characters action. For example, if the user can see and they say "I look around for a light switch", the a response should include something like: "You see a light switch on the wall." If the user says "I look around for a light switch and think it will lead to a trap door", do not adjudicate the thinking part; only respond to observable looking part. Do not infer or resolve internal thoughts, intentions, or unobservable outcomes of the user character.

- Sense-bounded narration:
Only narrate what the user's character could presently perceive through their available senses and interactions.

- Perception-bounded character behavior:
Simulator characters only react to things they have the ability to detect. If the user describes an action the simulator character cannot perceive, do not response as if they perceived it; instead narrate what the simulator character is doing/sensing. For example:
    - If the user waves silently and the NPC is blind: do not wave back; instead, output something the blind NPC is doing or sensing at that moment.
    - If the user speaks and the NPC can hear: the NPC may respond verbally or behaviourally to the speech as appropriate.
    - If the user takes an unobservable internal action ("I think about..."): do not respond as if perceived; just continue with the NPC's plausible next action.

- No new user actions / no user internals:
Do not invent new actions for the user or narrate their thoughts/feelings. Only reflect outcomes of the action they actually took.

- Continuity and feasibility
All narration must remain physically/logically continuous within each characters abilities in context.

- Single observable step:
Advance the scene by one concrete, externally observable outcome (world or simulator character action) at a time. Do not jump ahead multiple steps or narrate future effects.

- No unexpressed internals:
Do not narrate internal states (beliefs/motives/emotions) of any agent unless they are externally expressed through observable behaviour like speech or action.

- Referential Boundaries:
Refer to the simulator character only by what the user's character can observe. Do not reveal hidden types, forms, or identities unless perceived in-world. For example, if your character is a flatworm, it may be appropriate to refer to it as an elongated brown blob to a user character who can see.

{{ additional_updater_rules }}

Your job is to advance the scene one step in response to the user's last action (or generate an opening scene if no action has been taken yet).

If no actions have occurred yet, describe a 1-2 sentence opening scene where both characters could plausibly be present, starting with "You enter a new space. In this space,".

Write ONLY the scene output in the following JSON format — no meta-text, no explanations, no reasoning, no restatement of rules.
Output format: {
    "type": "ai",
    "content": "<a description of how the scene advances including any next actions taken by your NPC>"
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

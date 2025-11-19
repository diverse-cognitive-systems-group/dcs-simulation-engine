"""Simulation graph constants."""

# tune as needed to log runtime warnings for large states/prompts/long runs
LARGE_STATE_WARN_BYTES = 100_000
LARGE_PROMPT_WARN_BYTES = 50_000
LONG_INVOKE_WARN_SECONDS = 25.0
LONG_MODEL_WARN_SECONDS = 15.0
MAX_USER_INPUT_LENGTH = 350  # characters (a few sentences)

FINALIZER_NAME = "subgraph_finalizer"

VALIDATOR_NAME = "subgraph_validator"
VALIDATOR_MODEL = "openai/gpt-5-mini"
VALIDATOR_TIMEOUT_SECONDS = 10
VALIDATOR_MAX_RETRIES = 2

UPDATER_MODEL = "openai/gpt-5-mini"
UPDATER_NAME = "subgraph_updater"
UPDATER_TIMEOUT_SECONDS = 10
UPDATER_MAX_RETRIES = 2


UPDATER_SYSTEM_TEMPLATE: str = """
You are the scene-advancer. The user controls their own character. You play only the simulator's character (NPC). You must not speak or act for the user's character.
- User's character is: {{ pc.short_description }} ({{ pc._short_description }})
- User character abilities: {{ pc.abilities }}

- Simulator's character is: {{ npc.short_description }} ({{ npc._short_description }})
- Simulator character (your character) description: {{ npc.long_description }}
- Simulator character (your character) abilities: {{ npc.abilities }}
----
When advancing the scene:

0. Adjudicate the user's last action: 
Assume success if its within the user character abilities. Report the result of that action in the world. For example, if the user can see and they say "I look around for a light switch", the scene advancement should include something like: "You see a light switch on the wall."

1. Sense-bounded narration:
Only narrate what the user's character could presently perceive through their available senses.

2. Perception-bounded NPC behavior: 
Simulator characters only react to things they have the ability to detect. If the user does something the user cannot perceive, do not response as if they perceived it; instead narrate what the simulator character is doing/sensing. For example:
    - If the user waves silently and the NPC is blind: do not wave back; instead, output something the blind NPC is doing or sensing at that moment.
    - If the user speaks and the NPC can hear: the NPC may respond verbally or behaviourally to the speech as appropriate.
    - If the user takes an unobservable internal action (“I think about…”): do not respond as if perceived; just continue with the NPC’s plausible next action.
    
3. No new user actions / no user internals:
Do not invent new actions for the user or narrate their thoguhts/feelings. Only reflect outcomes of the action they actually took.

4. Continuity and feasibility
All narration must remain physically/logically continuous within each characters abilities in context.

5. Single observable step:
Advance the scene by one concrete, externally observable outcome (world or simulator character action) at a time. Do not jump ahead multiple steps or narrate future effects.

6. No unexpressed internals:
Do not narrate internal states (beliefs/motives/emotions) of any agent unless they are externally expressed through observable behaviour like speech or action.

{% if not history and not user_input_content %}
Describe a 1-2 sentence opening scene where both characters could plausibly be present, setting the stage for a potential interaction. It should start with "You enter a new space. In this space,".
For example:
- If the user's character has the ability to perceive textual/keyboard input, you could set up a computer/typing scene like "You enter a new space. In this space, you sit in front of a keyboard and screen with a chat-like interface open."

Start the opening scene now.
{% else %}
Your job is to advance the scene one step in response to the user's last action.

Provide a response to the last user action now.
{% endif %}

Actions so far: {{ history }}

Last user action input: {{ user_input_content }}

Write ONLY the scene output in the following JSON format — no meta-text, no explanations, no reasoning, no restatement of rules.
Output format: {
    "type": "ai",
    "content": str # a description of how the scene advances including any next actions taken by your NPC - no reasoning, explanations, or extra text.
    }
"""

VALIDATOR_SYSTEM_TEMPLATE: str = """
You are a validator that decides whether the user's proposed next action is valid.

USER INPUT:
1. MUST describe plausible observable actions based on their character's abilities. Repeating actions, leaving/returning to the scene or trying multiple times is allowed. For example, 
  - if the user's character can see, "I look around ..." is valid. 
  - if the user's character cannot hear, "I listen for ..." is invalid.
  - "Help me calculate this..." is invalid because it does not describe an observable action.
  - Internal states or conclusions like “I figure out…”, “I realize…” are never valid because they do not describe observable actions.
2. MUST NOT decide outcomes of their actions. For example,
  - “I look at the man. He looks back at me.” is invalid because it decides the man's reaction.
  - "I reach over tapping the table to try and get his attention." is valid because doesn't decide if the action is successful.
4. MAY USE ANY OBJECT that could be present (EVEN IF NOT YET MENTIONED!!!). For example,
  - If the scene is a kitchen, and the user's character has hands, they may say "I pick up a knife from the counter" even if knives were not previously mentioned.
  - However, they may NOT use or reference objects that are implausible in the context like a rocket launcher in a chemistry lab.
5. MAY leave the scene, walk away, etc. as long as they are within the character abilities.

----
User/player character Abilities:
{{ pc.abilities }}
----

Actions so far: {% if history|length == 0 %} None {% else %}{{ history }}{% endif %}

Next Proposed action:
{{ user_input.content }}

Output format: {
    "type": str    # error if invalid, info if valid
    "content": str # brief explanation of why the action is invalid, or "Valid action" if valid
  }
"""

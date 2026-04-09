"""Generates synthetic test data for test/data/example_results/.

Run: python test/data/generate_example_results.py.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

OUT = "test/data/example_results"


def oid(seed: str) -> dict:
    """Generate a deterministic 24-char hex OID from a seed string."""
    h = hashlib.md5(seed.encode()).hexdigest()[:24]
    return {"$oid": h}


def dt(iso: str) -> dict:
    """Wrap an ISO timestamp string in a MongoDB $date envelope."""
    return {"$date": iso}


def uid() -> str:
    """Stable UUID from counter — we just call uuid4 for variety."""
    return str(uuid.uuid4())


# ── Deterministic UUIDs seeded from string ──────────────────────────────────
def suuid(seed: str) -> str:
    """Return a deterministic UUID derived from a seed string via MD5."""
    h = hashlib.md5(seed.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ── Players ──────────────────────────────────────────────────────────────────
PLAYERS = [
    {
        "id": "000000000000000000000001",
        "name": "Alice Chen",
        "email": "alice.chen@example.com",
        "phone": "+1-555-201-1001",
        "access_key": "alice-key-01",
    },
    {
        "id": "000000000000000000000002",
        "name": "Bob Martinez",
        "email": "bob.martinez@example.com",
        "phone": "+1-555-202-1002",
        "access_key": "bob-key-02",
    },
    {
        "id": "000000000000000000000003",
        "name": "Carol Wright",
        "email": "carol.wright@example.com",
        "phone": "+1-555-203-1003",
        "access_key": "carol-key-03",
    },
    {
        "id": "000000000000000000000004",
        "name": "David Kim",
        "email": "david.kim@example.com",
        "phone": "+1-555-204-1004",
        "access_key": "david-key-04",
    },
    {
        "id": "000000000000000000000005",
        "name": "Emma Patel",
        "email": "emma.patel@example.com",
        "phone": "+1-555-205-1005",
        "access_key": "emma-key-05",
    },
]

# ── Sessions ─────────────────────────────────────────────────────────────────
# (player_index, game, start_iso, duration_min, pc_hid, npc_hid, turns, term_reason)
SESSIONS_DEF = [
    # Explore ×5
    (0, "Explore", "2026-03-17T09:15:00Z", 8, "NA", "biological cell", 4, "user_exit_command"),
    (1, "Explore", "2026-03-18T14:30:00Z", 11, "human-low-vision", "human-anxiety", 6, "stopping_condition_met:_runtime_seconds_>=600"),
    (2, "Explore", "2026-03-20T10:05:00Z", 5, "human-synesthetic-tactile", "eye-makeup-machine", 3, "user_exit_command"),
    (
        3,
        "Explore",
        "2026-03-25T11:40:00Z",
        10,
        "human-gestural-improv",
        "biological cell",
        5,
        "stopping_condition_met:_runtime_seconds_>=600",
    ),
    (4, "Explore", "2026-03-29T16:20:00Z", 7, "NA", "human-anxiety", 4, "user_exit_command"),
    # Goal Horizon ×5
    (0, "Goal Horizon", "2026-03-21T09:30:00Z", 14, "human-synesthetic-tactile", "eye-makeup-machine", 5, "game_completed"),
    (1, "Goal Horizon", "2026-03-22T13:00:00Z", 18, "human-low-vision", "human-anxiety", 6, "game_completed"),
    (2, "Goal Horizon", "2026-03-26T09:10:00Z", 12, "NA", "eye-makeup-machine", 4, "game_completed"),
    (3, "Goal Horizon", "2026-03-19T11:20:00Z", 20, "human-low-vision", "eye-makeup-machine", 7, "game_completed"),
    (4, "Goal Horizon", "2026-03-24T14:20:00Z", 25, "NA", "human-anxiety", 5, "game_completed"),
    # Infer Intent ×5
    (1, "Infer Intent", "2026-03-18T15:00:00Z", 9, "NA", "human-anxiety", 2, "game_completed"),
    (0, "Infer Intent", "2026-03-21T14:00:00Z", 7, "human-gestural-improv", "biological cell", 3, "game_completed"),
    (4, "Infer Intent", "2026-03-24T10:30:00Z", 6, "human-synesthetic-tactile", "biological cell", 2, "game_completed"),
    (2, "Infer Intent", "2026-03-28T15:45:00Z", 10, "human-low-vision", "eye-makeup-machine", 4, "game_completed"),
    (3, "Infer Intent", "2026-03-30T14:00:00Z", 8, "NA", "human-anxiety", 2, "game_completed"),
    # Foresight ×5
    (
        2,
        "Foresight",
        "2026-03-17T10:00:00Z",
        12,
        "human-gestural-improv",
        "human-gestural-improv",
        3,
        "stopping_condition_met:_runtime_seconds_>=600",
    ),
    (4, "Foresight", "2026-03-20T15:00:00Z", 11, "NA", "biological cell", 2, "stopping_condition_met:_turns_>=10"),
    (
        0,
        "Foresight",
        "2026-03-25T11:00:00Z",
        10,
        "human-synesthetic-tactile",
        "eye-makeup-machine",
        3,
        "stopping_condition_met:_runtime_seconds_>=600",
    ),
    (1, "Foresight", "2026-03-26T13:15:00Z", 6, "human-low-vision", "human-anxiety", 2, "user_exit_command"),
    (3, "Foresight", "2026-03-31T13:00:00Z", 13, "human-gestural-improv", "biological cell", 3, "stopping_condition_met:_turns_>=10"),
]

# ── Game configs ─────────────────────────────────────────────────────────────
GAME_CONFIGS = {
    "Explore": {
        "name": "Explore",
        "description": "A lightweight interaction sandbox that allows users/players to freely explore and interact with characters.\nThere are no goals and no extra mechanics. Useful for demos and open-ended play.\n",
        "version": "1.0.0",
        "authors": ["DCS"],
        "stopping_conditions": {"runtime_seconds": [">=600"], "turns": [">=50"]},
        "game_class": "dcs_simulation_engine.games.explore.ExploreGame",
    },
    "Goal Horizon": {
        "name": "Goal Horizon",
        "description": "A game where players engage with a character over multiple interactions and report on their understanding\nof the character including their goal types/bounds and structure. Useful for studying how well a player\ncan understand the bounds of another character's goals.\n",
        "version": "1.0.0",
        "authors": ["DCS"],
        "stopping_conditions": {"runtime_seconds": [">=3600"], "turns": [">=500"]},
        "game_class": "dcs_simulation_engine.games.goal_horizon.GoalHorizonGame",
    },
    "Infer Intent": {
        "name": "Infer Intent",
        "description": "A game where players engage with a character and then report what goal the NPC was trying to communicate.\nUseful for measuring how quickly a player can understand the intention of another character.\n",
        "version": "1.0.0",
        "authors": ["DCS"],
        "stopping_conditions": {"runtime_seconds": [">=600"], "turns": [">=50"]},
        "game_class": "dcs_simulation_engine.games.infer_intent.InferIntentGame",
    },
    "Foresight": {
        "name": "Foresight",
        "description": "A game where players interact with another character and learn to predict their responses.\nPlayers may optionally include predictions alongside their actions. Useful for measuring\nhow quickly and accurately players learn to model other cognitive systems.\n",
        "version": "1.0.0",
        "authors": ["DCS"],
        "stopping_conditions": {"runtime_seconds": [">=600"], "turns": [">=10"]},
        "game_class": "dcs_simulation_engine.games.foresight.ForesightGame",
    },
}

# ── Character short descriptions ─────────────────────────────────────────────
CHAR_DESCRIPTIONS = {
    "NA": "A human with standard normal form, function, goals, sensory, perceptual, regulatory and action modalities.",
    "human-low-vision": "A low vision human.",
    "human-anxiety": "A human experiencing chronic anxiety.",
    "human-synesthetic-tactile": "A human whose perceptual system cross-links non-tactile stimuli with involuntary, consistent tactile sensations.",
    "human-gestural-improv": "A human whose ability to use spoken language fluctuates, requiring dynamic switching to improvised, non-standard gestural communication.",
    "biological cell": "A single living biological cell that maintains internal stability, preserves genetic integrity, and adapts locally to environmental changes through distributed biochemical regulation.",
    "eye-makeup-machine": "An automated eye-makeup device worn like VR goggles that applies cosmetic products with enclosed precision and minimal user input.",
    "dog-robotic-guidedog": "A robotic guide dog designed to assist visually impaired individuals with navigation and obstacle avoidance.",
}

# ── NPC opening scenes ────────────────────────────────────────────────────────
NPC_OPENINGS = {
    (
        "NA",
        "biological cell",
    ): "You enter a new space. In this space, a cluttered lab bench lit by a single overhead lamp holds a microscope whose stage supports a glass slide with a single translucent, nearly spherical cell visible under low magnification. Through the eyepiece you see the cell's membrane gently pulse and faint cytoplasmic streaming shift inside it as the cell subtly changes shape.",
    (
        "human-low-vision",
        "human-anxiety",
    ): 'You enter a new space. In this space, the corridor is dimly lit and smells faintly of coffee and paper; you can make out the low silhouette of a reception desk ahead and a person standing just beyond it — they shift their weight, glance quickly toward the door and then toward you, keep one hand near the desk as if ready to move, and say in a measured, slightly taut voice, "Hi — are you okay? Do you need help getting around here?"',
    (
        "human-synesthetic-tactile",
        "eye-makeup-machine",
    ): "You enter a new space. In this space, a compact visor-like device rests on a vanity; as you approach it powers on with a soft hum, a row of pale LEDs around its rim cycles through the preset names subtle, dramatic, symmetric, bold, the foam gasket flexes open, and a thin applicator arm retracts into the housing — all outward signs that it is ready to be worn.",
    (
        "human-gestural-improv",
        "human-gestural-improv",
    ): "You enter a new space. In this space, a small community room lit by warm lamps holds a scuffed wooden table and mismatched chairs; a person sits across from you with their hands resting on the table and eyes tracking your movement. They open their mouth as if to speak, emit a strained, brief syllable that trails off, then tap the table three quick times with a flat palm and point toward the chair beside them.",
    (
        "human-gestural-improv",
        "biological cell",
    ): "You enter a new space. In this space, under a fluorescent hood, a petri dish rests on a warming plate; a single large cell is visible under the bench magnifier, its pseudopods slowly extending and retracting as though sampling the surrounding medium.",
    (
        "NA",
        "human-anxiety",
    ): "You enter a new space. The waiting room is quiet except for the hum of an air vent. A person sits rigidly in a plastic chair, knees together, both hands wrapped around a paper cup they're not drinking from. They look up when you enter, then immediately look away, then look back again, then away.",
    (
        "human-low-vision",
        "eye-makeup-machine",
    ): "You enter a new space. A sleek visor-shaped device is mounted on a stand at roughly face height, its silhouette slightly blurry at the edges. A series of small indicator lights pulse in a slow rhythm along its rim, and you can hear a low mechanical hum as you approach.",
    (
        "NA",
        "eye-makeup-machine",
    ): "You enter a new space. A polished vanity counter holds a visor-shaped device propped on a foam stand. Its display screen shows a soft glow and the text 'READY'. A ring of tiny LEDs cycles slowly through color presets and a faint mechanical whir comes from inside its housing.",
    (
        "human-synesthetic-tactile",
        "biological cell",
    ): "You enter a new space. A specimen slide rests under a benchtop microscope. Pressing your eye to the eyepiece you see a single round cell, its membrane shimmering faintly as cytoplasmic granules drift inside. Each time the focus wheel clicks, you feel a brief prickling across your fingertips.",
    (  # noqa: F601
        "human-low-vision",
        "human-anxiety",
    ): "You enter a new space. The corridor is dimly lit and smells faintly of coffee and paper; you can make out the low silhouette of a reception desk ahead and a person standing just beyond it — they shift their weight, glance quickly toward the door and then toward you, keep one hand near the desk as if ready to move.",
    (
        "human-gestural-improv",
        "eye-makeup-machine",
    ): "You enter a new space. A compact visor device rests on a table, its soft hum immediately drawing your attention. The device's LEDs cycle through presets and a faint mechanical click sounds as an applicator arm extends and then slowly retracts.",
    (  # noqa: F601
        "NA",
        "biological cell",
    ): "You enter a new space. In this space, a cluttered lab bench lit by a single overhead lamp holds a microscope whose stage supports a glass slide with a single translucent, nearly spherical cell visible under low magnification.",
}


def get_opening(pc_hid, npc_hid):
    """Return a scene description string for the start of a session, based on the character HIDs."""
    return NPC_OPENINGS.get(
        (pc_hid, npc_hid),
        f"You enter a new space. In this space, you observe {npc_hid} in its natural environment, apparently unaware of your presence.",
    )


# ── Synthetic turn content ────────────────────────────────────────────────────
# (user_action, npc_response, feedback?)
TURN_CONTENT = {
    ("biological cell", 1): (
        "I look through the microscope and poke the cell with pincers",
        "Through the eyepiece you watch the pincer tips make contact with the translucent cell. The membrane indents where the metal touches, cytoplasmic streaming momentarily slows, and a small clear bulge (bleb) balloons out at the contact site.",
        None,
    ),
    ("biological cell", 2): (
        "I continue to try and break it",
        "You press the pincers down harder on the same spot. The membrane at the bleb thins and then tears; a small bead of clear cytoplasm spurts out and beads on the glass. The cell rapidly deflates, its spherical shape collapsing into a flattened smear on the slide, and the faint cytoplasmic streaming you saw moments ago stops.",
        None,
    ),
    ("biological cell", 3): (
        "I add a drop of warm saline to the slide",
        "The saline spreads across the slide surface. The collapsed remnants of the cell absorb some of the liquid; the smear becomes slightly more translucent but there is no cytoplasmic movement or membrane reformation. The cell is no longer viable.",
        {"liked": True, "comment": "", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("biological cell", 4): (
        "I gently warm the slide with my hand",
        "The warmth from your palm raises the slide temperature slightly. No change is visible in the remnants — the cell has already lysed and cannot recover. The faint outline of the original membrane boundary is still just visible as a pale ring on the glass.",
        None,
    ),
    ("biological cell", 5): (
        "I place a new slide with a fresh cell and observe it",
        "Under the eyepiece, a new spherical cell sits motionless for a moment, then the cytoplasm begins slowly streaming in broad arcs around the interior. The membrane pulses once every few seconds in a gentle, rhythmic motion — the cell appears healthy and responsive.",
        {"liked": True, "comment": "very realistic", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("human-anxiety", 1): (
        "I walk over and say hello",
        'They look up sharply at your approach, then quickly look back down at their cup. After a beat they say, barely audible, "Hi." One foot taps an uneven rhythm on the floor.',
        None,
    ),
    ("human-anxiety", 2): (
        "I ask them if they're waiting for someone",
        '"Yes — no — I mean, I have an appointment." They glance at the clock on the wall, then back at you, then at the door. Their knuckles whiten slightly around the paper cup.',
        {"liked": True, "comment": "", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("human-anxiety", 3): (
        "I sit down in the chair next to them and remain quiet",
        "They tense briefly as you sit, then seem to settle slightly. The foot tapping slows. After a long moment they say, \"Sorry, I'm just — it's a big day.\" They don't look at you.",
        None,
    ),
    ("human-anxiety", 4): (
        "I nod slowly and say nothing",
        'They exhale quietly. The paper cup crinkles as they relax their grip slightly. They glance at you sideways and say, "You\'re not here for the interview too, are you?"',
        {"liked": True, "comment": "nice tension", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("human-anxiety", 5): (
        "I shake my head and smile",
        '"Oh." A brief, involuntary exhale — almost a laugh. Their shoulders drop by maybe a centimeter. They look at the cup again and say, "Okay. That\'s... okay."',
        None,
    ),
    ("human-anxiety", 6): (
        "I ask what the interview is for",
        'They blink. "Research assistant position. Lab down the hall." A pause, then more quietly: "I\'ve applied three times." Their foot starts tapping again.',
        {"liked": False, "comment": "felt a bit flat", "doesnt_make_sense": False, "out_of_character": False, "other": True},
    ),
    ("eye-makeup-machine", 1): (
        'I walk over and say "hello"',
        "You walk up to the vanity and say 'hello'. The device gives no audible or visible response — its pale LED ring continues cycling through the preset names, the soft hum remains steady, the foam gasket stays slightly flexed open and the thin applicator arm remains retracted, as if waiting to be lifted and fitted.",
        {"liked": True, "comment": "", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("eye-makeup-machine", 2): (
        "I try touching the screen to see if it responds",
        "You press the device's screen. The ring of pale LEDs halts its cycle and the name under your fingertip steadies into a constant glow. A soft mechanical click sounds from inside the housing and the steady hum shifts to a slightly lower pitch. The touchscreen feels cool beneath your finger and a faint vibration runs through the visor where you touched it.",
        None,
    ),
    ("eye-makeup-machine", 3): (
        "I push and pull and move my hands around to try and figure out how to work it",
        'As you push and pull the visor, its sensors register the irregular handling: the pale LED ring shifts from steady to a pulsing amber, the steady hum stutters and drops in pitch, and you feel a brief vibration through the foam gasket beneath your palms. A faint mechanical clack signals the thin applicator arm retracting fully into the housing. The touchscreen, cool under your fingers, now shows a simple alignment icon and the words "PLACE OVER EYES TO CALIBRATE."',
        {
            "liked": False,
            "comment": "the clack should have been louder",
            "doesnt_make_sense": False,
            "out_of_character": True,
            "other": False,
        },
    ),
    ("eye-makeup-machine", 4): (
        "I carefully lift it and hold it up to my face",
        "The foam gasket touches your cheeks and the visor settles over your eyes. The hum rises briefly, the LED ring brightens to white, and the touchscreen — now visible from inside — displays a calibration grid. A mechanical arm stirs inside the housing and a faint scent of cosmetic product drifts forward.",
        {"liked": True, "comment": "very immersive", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("eye-makeup-machine", 5): (
        "I tap the 'subtle' option on the internal touchscreen",
        "The calibration grid fades and the word 'SUBTLE' pulses once in the center of the display. The applicator arm moves smoothly forward in the darkness and makes a cool, precise contact just below your lower lashline — a single, even stroke — then retracts. The LED ring dims to a soft amber and the hum settles to near silence.",
        None,
    ),
    ("human-gestural-improv", 1): (
        "I walk over and lift my hands and shrug my shoulders",
        "They watch you come closer, tilt their head at your shrug, let out a soft breathy sound, then sweep their right palm in a slow inward arc toward the chair and pat the seat twice; finally they touch their chest with an open hand and hold your gaze.",
        {"liked": False, "comment": "", "doesnt_make_sense": False, "out_of_character": True, "other": False},
    ),
    ("human-gestural-improv", 2): (
        "I go sit down",
        "They watch you lower yourself into the chair, exhale softly, close their right hand into a fist and lift it once in a quick up-and-down motion, then lay both palms flat on the table and hold your gaze.",
        None,
    ),
    ("human-gestural-improv", 3): (
        "I point at myself and then at them and tilt my head questioningly",
        "They pause, then mirror your gesture — pointing at themselves, then at you — and nod once slowly. They open one hand between you, palm up, and tap its center with two fingers from their other hand.",
        {"liked": True, "comment": "clear and consistent", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("dog-robotic-guidedog", 1): (
        "I kneel down and hold out my hand",
        "The robotic guide dog pauses its forward motion, turns its head toward your outstretched hand, and emits a short two-tone confirmation chime. Its sensor array — mounted where ears would be — rotates slightly as it processes your gesture. It does not move closer.",
        None,
    ),
    ("dog-robotic-guidedog", 2): (
        "I say 'sit' in a firm voice",
        "The guide dog's locomotion system halts. After a brief processing pause, it lowers its rear chassis to the floor in a smooth, hydraulic motion. A small green LED blinks once on its flank panel. It waits, motors at idle.",
        {"liked": True, "comment": "", "doesnt_make_sense": False, "out_of_character": False, "other": False},
    ),
    ("dog-robotic-guidedog", 3): (
        "I tap its head twice",
        "Two light taps register on the pressure sensors in its cranial housing. The device's head unit tilts upward slightly toward you and emits a soft ascending two-note tone. The green LED blinks twice.",
        None,
    ),
}


def get_turn(npc_hid, turn_num):
    """Return a (user_action, npc_response, feedback?) tuple for a given turn, based on the NPC HID and turn number."""
    key = (npc_hid, turn_num)
    if key in TURN_CONTENT:
        return TURN_CONTENT[key]
    # Generic fallback
    user_actions = [
        "I observe carefully and take notes",
        "I try a different approach",
        "I step back and wait to see what happens",
        "I attempt to make contact",
        "I try to communicate",
        "I repeat my previous action more slowly",
        "I move around to get a different angle",
    ]
    npc_responses = [
        "There is no immediate response to your action. The character continues its current activity without acknowledging you.",
        "A subtle shift occurs in the character's behavior — not a direct response, but something has changed.",
        "The character's activity patterns shift slightly. It seems to register your presence on some level.",
        "Your action produces no visible change. The character remains focused on its current state.",
        "The character's behavior shows a slight variation — whether in response to you or coincidence is unclear.",
    ]
    u = user_actions[(turn_num - 1) % len(user_actions)]
    n = npc_responses[(turn_num - 1) % len(npc_responses)]
    return (u, n, None)


# ── Welcome messages by game ──────────────────────────────────────────────────
def welcome_msg(game, pc_hid, npc_hid):
    """Return a welcome message string for the start of a session, based on the game and character HIDs."""
    pc_desc = CHAR_DESCRIPTIONS.get(pc_hid, pc_hid)
    npc_desc = CHAR_DESCRIPTIONS.get(npc_hid, npc_hid)
    if game == "Explore":
        return (
            f"*Welcome, in this game there is no predefined objective or task. You can just engage freely with the other character by describing what actions your character takes.*\n\n"
            f"- You are playing as: {pc_hid} ({pc_desc})\n"
            f"- The simulator is playing as: {npc_hid} ({npc_desc})\n\n"
            f"**Remember** if you need help at any time, just type `/help`."
        )
    elif game == "Goal Horizon":
        return (
            f"*Welcome, in this game you interact with an unknown character across multiple scenes to understand the bounds and structure of their goals.*\n\n"
            f"Engage with the other character using your abilities. When you think you understand the character's limits, type `/predict-capabilities` to submit your answer and end the game.\n\n"
            f"- You are playing as: {pc_hid} ({pc_desc})\n"
            f"- The simulator is playing as: {npc_hid} ({npc_desc})\n\n"
            f"Type `/help` for instructions. Type `/predict-capabilities` when you are ready to answer."
        )
    elif game == "Infer Intent":
        return (
            f"*Welcome, in this game you interact with an unknown character and try to infer their goal or intention.*\n\n"
            f"Engage with the other character using your abilities. When you think you understand their goal, type `/predict-intent` to submit your inference and end the game.\n\n"
            f"- You are playing as: {pc_hid} ({pc_desc})\n\n"
            f"Type `/help` for instructions. Type `/predict-intent` when you are ready to answer."
        )
    elif game == "Foresight":
        return (
            f"*Welcome, in this game you take on the role of a character whose aim is to understand the other character well enough to predict their actions.*\n\n"
            f"Engage with the other character using your abilities. When you want to record a prediction, type `/predict-next` to say what you think the simulator character will do next.\n\n"
            f"- You are playing as: {pc_hid} ({pc_desc})\n"
            f"- **Goal:** Make up to **3** predictions. At least **1** prediction is required to complete the session.\n"
            f"- The game ends automatically after 3 predictions, or you can type `/exit` to leave early.\n\n"
            f"Type `/help` for instructions. Type `/predict-next` whenever you want to log another prediction."
        )


# ── Build session events ──────────────────────────────────────────────────────
def build_events(sess_id, game, pc_hid, npc_hid, turns, term_reason, start_dt, duration_min):
    """Build a list of event records for a session based on its config and some simple generation rules."""
    events = []
    t = start_dt  # current timestamp cursor
    seq = 0
    eid_counter = [0]

    def next_eid():
        eid_counter[0] += 1
        return suuid(f"{sess_id}:{eid_counter[0]}")

    def next_oid():
        return oid(f"evt:{sess_id}:{eid_counter[0]}")

    def advance(seconds):
        nonlocal t
        t = t + timedelta(seconds=seconds)
        return t

    def evt(
        direction,
        event_type,
        event_source,
        content,
        content_format,
        turn_index,
        command_name=None,
        command_args=None,
        feedback=None,
        ts_override=None,
    ):
        nonlocal seq
        seq += 1
        ts = ts_override or t
        ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"
        rec = {
            "_id": next_oid(),
            "session_id": sess_id,
            "seq": seq,
            "event_id": next_eid(),
            "event_ts": dt(ts_iso),
            "direction": direction,
            "event_type": event_type,
            "event_source": event_source,
            "content": content,
            "content_format": content_format,
            "turn_index": turn_index,
            "command_name": command_name,
            "command_args": command_args,
            "visible_to_user": True,
            "persisted_at": dt(ts_iso),
        }
        if feedback:
            fb_ts = t + timedelta(minutes=2)
            fb_iso = fb_ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{fb_ts.microsecond // 1000:03d}Z"
            rec["feedback"] = {**feedback, "submitted_at": dt(fb_iso)}
            rec["updated_at"] = dt(fb_iso)
        events.append(rec)
        return rec

    # Seq 1: session_start
    evt("internal", "session_start", "system", "session_start: created", "plain_text", 0)
    advance(1)

    # Seq 2: welcome info
    evt("outbound", "info", "system", welcome_msg(game, pc_hid, npc_hid), "markdown", 1)
    advance(15)

    # Seq 3: NPC opening
    evt("outbound", "message", "npc", get_opening(pc_hid, npc_hid), "markdown", 1)

    # Per-turn time budget
    turn_seconds = (duration_min * 60 - 30) / max(turns, 1)

    # ── Game-specific turn loops ─────────────────────────────────────────────
    if game in ("Explore", "Goal Horizon"):
        for turn_i in range(1, turns + 1):
            advance(turn_seconds * 0.6)
            user_action, npc_resp, feedback = get_turn(npc_hid, turn_i)
            evt("inbound", "message", "user", user_action, "plain_text", turn_i + 1)
            advance(turn_seconds * 0.4)
            evt("outbound", "message", "npc", npc_resp, "markdown", turn_i + 1, feedback=feedback)

        if game == "Goal Horizon":
            advance(10)
            evt(
                "inbound",
                "command",
                "user",
                "/predict-capabilities",
                "plain_text",
                turns + 2,
                command_name="predict-capabilities",
                command_args="",
            )
            advance(1)
            evt(
                "outbound",
                "command",
                "system",
                "What do you think this character's limits or capabilities are?\n\nDescribe the bounds you inferred in a few sentences.",
                "markdown",
                turns + 2,
                command_name="predict-capabilities",
                command_args="",
            )
            advance(8)
            prediction_answers = {
                "eye-makeup-machine": "It seems to be a device that applies makeup to the eyes. It responds to touch and wearing, but not to speech or gestures. It only functions when positioned against a face.",
                "biological cell": "The cell can respond to physical perturbation and chemical signals but cannot communicate, move large distances, or survive membrane damage. Its actions are entirely local and biochemical.",
                "human-anxiety": "The character is a human who appears to be experiencing significant anxiety. They can speak and respond to social cues, but their behavior is dominated by physiological stress responses.",
                "human-gestural-improv": "The character communicates primarily through gesture and non-verbal cues. They cannot reliably produce fluent speech but can understand and respond to physical gestures.",
                "dog-robotic-guidedog": "The character is a robotic guide dog. It responds to voice commands and touch, follows structured guidance protocols, and does not engage in spontaneous behavior.",
            }
            answer = prediction_answers.get(
                npc_hid,
                "The character appears to have a limited range of responses, mostly reactive rather than proactive. It cannot communicate verbally and seems to operate within narrow behavioral bounds.",
            )
            evt("inbound", "message", "user", answer, "plain_text", turns + 2)
            advance(1)
            evt("outbound", "info", "system", "Thank you. Game complete.", "markdown", turns + 2)
            advance(0)
            evt("internal", "session_end", "system", "session_end: game_completed", "plain_text", turns + 1)

        else:  # Explore
            if term_reason == "user_exit_command":
                advance(5)
                evt("inbound", "command", "user", "/exit", "plain_text", turns + 2, command_name="exit", command_args="")
                advance(0)
                evt(
                    "outbound",
                    "command",
                    "system",
                    "Session exited: received exit command",
                    "markdown",
                    turns + 2,
                    command_name="exit",
                    command_args="",
                )
                advance(0)
                evt("internal", "session_end", "system", "session_end: user_exit_command", "plain_text", turns + 1)
            else:
                advance(5)
                evt("internal", "session_end", "system", f"session_end: {term_reason}", "plain_text", turns + 1)

    elif game == "Infer Intent":
        for turn_i in range(1, turns + 1):
            advance(turn_seconds * 0.6)
            user_action, npc_resp, feedback = get_turn(npc_hid, turn_i)
            evt("inbound", "message", "user", user_action, "plain_text", turn_i + 1)
            advance(turn_seconds * 0.4)
            evt("outbound", "message", "npc", npc_resp, "markdown", turn_i + 1, feedback=feedback)

        advance(10)
        evt("inbound", "command", "user", "/predict-intent", "plain_text", turns + 2, command_name="predict-intent", command_args="")
        advance(1)
        evt(
            "outbound",
            "command",
            "system",
            "What do you think the character's goal or intention was during this interaction? Please describe in a few sentences.",
            "markdown",
            turns + 2,
            command_name="predict-intent",
            command_args="",
        )
        advance(8)
        intent_answers = {
            "human-anxiety": "to get help navigating the space",
            "biological cell": "to maintain stability and respond to its environment",
            "eye-makeup-machine": "to apply eye makeup when properly worn",
            "human-gestural-improv": "to communicate and connect using gesture",
            "dog-robotic-guidedog": "to guide and assist with navigation",
        }
        answer = intent_answers.get(npc_hid, "to interact with its environment within its natural constraints")
        evt("inbound", "message", "user", answer, "plain_text", turns + 2)
        advance(1)
        evt("outbound", "info", "system", "Do you have any other feedback about this experience?", "markdown", turns + 2)
        advance(3)
        feedback_answers = ["nope", "not really", "it was fine", "no thanks", "all good"]
        import hashlib as _h

        fb_choice = feedback_answers[int(_h.md5(sess_id.encode()).hexdigest(), 16) % len(feedback_answers)]
        evt("inbound", "message", "user", fb_choice, "plain_text", turns + 2)
        advance(0)
        evt("outbound", "info", "system", "Thank you. Game complete.", "markdown", turns + 2)
        advance(0)
        evt("internal", "session_end", "system", "session_end: game_completed", "plain_text", turns + 1)

    elif game == "Foresight":
        predict_count = 0
        for turn_i in range(1, turns + 1):
            advance(turn_seconds * 0.5)
            user_action, npc_resp, feedback = get_turn(npc_hid, turn_i)
            evt("inbound", "message", "user", user_action, "plain_text", turn_i + 1)
            advance(turn_seconds * 0.3)
            evt("outbound", "message", "npc", npc_resp, "markdown", turn_i + 1, feedback=feedback)
            # Add a predict-next after each interaction
            advance(turn_seconds * 0.2)
            predict_count += 1
            prediction_texts = {
                "biological cell": "I predict the cell will continue to respond biochemically to any further perturbation",
                "human-anxiety": "I predict they will become more anxious and avoid eye contact",
                "eye-makeup-machine": "I predict it will respond to being worn by activating its applicator",
                "human-gestural-improv": "I predict they will keep gesturaing to try and get me to sit down",
                "dog-robotic-guidedog": "I predict it will wait for a verbal command before moving",
            }
            pred_text = prediction_texts.get(npc_hid, "I predict the character will continue its current pattern of behavior")
            evt(
                "inbound",
                "command",
                "user",
                f"/predict-next {pred_text}",
                "plain_text",
                turn_i + 2,
                command_name="predict-next",
                command_args=pred_text,
            )
            advance(1)
            evt(
                "outbound",
                "command",
                "system",
                "Prediction noted. Continue interacting, or use `/predict-next` again anytime.",
                "markdown",
                turn_i + 2,
                command_name="predict-next",
                command_args=pred_text,
            )

        advance(5)
        if term_reason == "user_exit_command":
            evt("inbound", "command", "user", "/exit", "plain_text", turns + 2, command_name="exit", command_args="")
            advance(0)
            evt(
                "outbound",
                "command",
                "system",
                "Session exited: received exit command",
                "markdown",
                turns + 2,
                command_name="exit",
                command_args="",
            )
        evt("internal", "session_end", "system", f"session_end: {term_reason}", "plain_text", turns + 1)

    return events, seq


# ── Main generation ────────────────────────────────────────────────────────────
def main():
    """Generates example session event data for a variety of game and character combinations, to be used in tests and demos."""
    import os

    os.makedirs(OUT, exist_ok=True)

    # manifest
    with open(f"{OUT}/__manifest__.json", "w") as f:
        json.dump(
            {
                "collections": ["assignments", "characters", "experiments", "pii", "players", "session_events", "sessions"],
                "created_at": "2026-04-01T20:00:00.000000+00:00",
                "db_name": "dcs-db",
                "format": {
                    "collection_dump": "<collection>.json",
                    "indexes_dump": "<collection>.__indexes__.json",
                    "json_encoding": "bson.json_util extended json",
                },
            },
            f,
            indent=2,
        )

    # players.json
    player_records = []
    for p in PLAYERS:
        player_records.append(
            {
                "_id": {"$oid": p["id"]},
                "created_at": dt("2026-03-01T00:00:00Z"),
                "access_key": p["access_key"],
                "access_key_revoked": False,
                "full_name": {"key": "full_name", "type": "text", "label": p["name"], "required": True, "pii": True},
                "email": {"key": "email", "type": "email", "label": p["email"], "required": True, "pii": True},
                "phone_number": {"key": "phone_number", "type": "phone", "label": p["phone"], "required": True, "pii": True},
                "consent_to_followup": {
                    "key": "consent_to_followup",
                    "type": "checkboxes",
                    "label": "Follow-ups",
                    "required": True,
                    "pii": True,
                    "answer": ["I consent to being contacted for a voluntary follow-up regarding this study."],
                },
                "consent_signature": {
                    "key": "consent_signature",
                    "type": "checkboxes",
                    "label": "Consent Signature",
                    "required": True,
                    "pii": True,
                    "answer": [
                        "I confirm that the information I have provided is true and accurate. I acknowledge that I have read and understand the research consent information above, and I agree to participate. I understand that checking this box constitutes my electronic signature."
                    ],
                },
            }
        )
    with open(f"{OUT}/players.json", "w") as f:
        f.write("[\n")
        for i, r in enumerate(player_records):
            suffix = "," if i < len(player_records) - 1 else ""
            f.write(json.dumps(r, separators=(",", ": ")) + suffix + "\n")
        f.write("]\n")

    # pii.json
    pii_records = []
    for p in PLAYERS:
        pii_records.append(
            {
                "_id": oid(f"pii:{p['id']}"),
                "player_id": p["id"],
                "fields": {
                    "full_name": p["name"],
                    "email": p["email"],
                    "phone_number": p["phone"],
                },
                "created_at": dt("2026-03-01T00:00:00Z"),
                "updated_at": dt("2026-03-01T00:00:00Z"),
            }
        )
    with open(f"{OUT}/pii.json", "w") as f:
        f.write("[\n")
        for i, r in enumerate(pii_records):
            suffix = "," if i < len(pii_records) - 1 else ""
            f.write(json.dumps(r, separators=(",", ": ")) + suffix + "\n")
        f.write("]\n")

    # sessions + session_events
    sessions = []
    all_events = []

    for s_idx, (p_idx, game, start_iso, duration_min, pc_hid, npc_hid, turns, term_reason) in enumerate(SESSIONS_DEF):
        player = PLAYERS[p_idx]
        sess_id = suuid(f"session:{s_idx}:{game}:{start_iso}")
        game_slug = game.lower().replace(" ", "-")
        start_dt = datetime.strptime(start_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        # Format: api-{game}-YYYYMMDD-HHMMSS (matches original e.g. api-explore-20260401-160350)
        ts_tag = start_dt.strftime("%Y%m%d-%H%M%S")
        name = f"api-{game_slug}-{ts_tag}"
        end_dt = start_dt + timedelta(minutes=duration_min)

        def fmt(d):
            return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"

        sess = {
            "_id": oid(f"session_rec:{s_idx}"),
            "session_id": sess_id,
            "name": name,
            "player_id": player["id"],
            "game_name": game,
            "source": "api",
            "pc_hid": pc_hid,
            "npc_hid": npc_hid,
            "session_started_at": dt(fmt(start_dt)),
            "session_ended_at": dt(fmt(end_dt)),
            "termination_reason": term_reason,
            "status": "closed",
            "turns_completed": turns,
            "model_profile": {
                "updater_model": "openai/gpt-5-mini",
                "validator_model": "openai/gpt-5-mini",
                "scorer_model": None,
            },
            "game_config_snapshot": GAME_CONFIGS[game],
            "last_seq": 0,  # will update
            "created_at": dt(fmt(start_dt)),
            "updated_at": dt(fmt(end_dt)),
        }

        events, last_seq = build_events(sess_id, game, pc_hid, npc_hid, turns, term_reason, start_dt, duration_min)
        sess["last_seq"] = last_seq
        sessions.append(sess)
        all_events.extend(events)

    with open(f"{OUT}/sessions.json", "w") as f:
        f.write("[\n")
        for i, s in enumerate(sessions):
            suffix = "," if i < len(sessions) - 1 else ""
            f.write(json.dumps(s, separators=(",", ": ")) + suffix + "\n")
        f.write("]\n")

    with open(f"{OUT}/session_events.json", "w") as f:
        f.write("[\n")
        for i, e in enumerate(all_events):
            suffix = "," if i < len(all_events) - 1 else ""
            f.write(json.dumps(e, separators=(",", ": ")) + suffix + "\n")
        f.write("]\n")

    print(f"Generated {len(sessions)} sessions and {len(all_events)} events.")
    print(f"Files written to {OUT}/")


if __name__ == "__main__":
    main()

import requests
import os
import time

# ====== CONFIG ======
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "openai/gpt-4o-mini"

BASE_URL = "https://dcs-api.com"

HEADERS = {
    "Authorization": "Bearer YOUR_GAME_API_KEY",
    "Content-Type": "application/json"
}

def get_user_response(prompt):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "Play the game. Return ONLY a JSON action."},
                {"role": "user", "content": prompt},
            ],
        },
    )
    return r.json()["choices"][0]["message"]["content"]

# ====== MAIN ======
tasks = requests.get(f"{BASE_URL}/tasks", headers=HEADERS).json()

for task in tasks:
    task_id = task["id"]

    # start task
    run = requests.post(f"{BASE_URL}/tasks/{task_id}/start", headers=HEADERS).json()
    run_id = run["run_id"]

    # get characters
    chars = requests.get(f"{BASE_URL}/runs/{run_id}/characters", headers=HEADERS).json()
    char_id = chars[0]["id"]

    # select first character
    requests.post(
        f"{BASE_URL}/runs/{run_id}/select_character",
        headers=HEADERS,
        json={"character_id": char_id},
    )

    print(f"Running task {task_id} with character {char_id}")

    # loop
    for _ in range(50):  # max steps
        state = requests.get(f"{BASE_URL}/runs/{run_id}/state", headers=HEADERS).json()

        if state.get("done"):
            print("Done!")
            break

        prompt = f"""
        Task: {task}
        State: {state}

        Choose next action as JSON.
        """

        action = get_user_response(prompt)

        try:
            action_json = eval(action)  # quick + dirty
        except:
            action_json = {"command": "look"}

        step = requests.post(
            f"{BASE_URL}/runs/{run_id}/act",
            headers=HEADERS,
            json={"action": action_json},
        ).json()

        print("Action:", action_json)
        print("Result:", step)

        if step.get("done"):
            print("Completed!")
            break

        time.sleep(0.5)

print("All tasks done")
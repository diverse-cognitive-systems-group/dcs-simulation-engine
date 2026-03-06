"""Analysis shared helper functions."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def human_duration(seconds: float) -> str:
    """Convert seconds to human-friendly duration string (e.g. '1h 5m 3s')."""
    td = timedelta(seconds=int(seconds))
    d = td.days
    h, r = divmod(td.seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def parse_dt(x):
    """Handle ISO strings and Mongo-like {'$date': ...} objects; return pandas.Timestamp or NaT."""
    if x is None:
        return pd.NaT
    if isinstance(x, dict) and "$date" in x:
        return pd.to_datetime(x["$date"], utc=True, errors="coerce")
    if isinstance(x, str):
        return pd.to_datetime(x, utc=True, errors="coerce")
    return pd.to_datetime(x, utc=True, errors="coerce")


def load_runs_ndjson(path) -> pd.DataFrame:
    """Load runs.ndjson into a DataFrame (one row per run)."""
    path = Path(path)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    df = pd.json_normalize(rows, sep=".")
    # Helpful parsed columns
    df["start_dt"] = df.get("start_ts", pd.Series([None] * len(df))).apply(parse_dt)
    df["end_dt"] = df.get("end_ts", pd.Series([None] * len(df))).apply(parse_dt)
    if "runtime_seconds" in df.columns:
        df["runtime_human"] = df["runtime_seconds"].apply(lambda s: human_duration(float(s)) if pd.notna(s) else None)
    return df


def run_summary(run: dict) -> dict:
    """Minimal, analysis-friendly summary for one run dict.
    (Return dict so you can print it, put it in a df, or JSON-dump it.)
    """
    start_dt = parse_dt(run.get("start_ts"))
    end_dt = parse_dt(run.get("end_ts"))
    runtime_s = run.get("runtime_seconds")
    runtime_h = human_duration(float(runtime_s)) if runtime_s is not None else None

    # Pull transcript (state.history)
    history = ((run.get("state") or {}).get("history")) or []
    n_msgs = len(history)
    nhuman = sum(1 for m in history if (m.get("type") == "human"))
    n_ai = sum(1 for m in history if (m.get("type") == "ai"))

    # Completion form answers, if present
    completion = ((run.get("state") or {}).get("forms") or {}).get("completion_form") or {}
    answers = {}
    for q in completion.get("questions", []) or []:
        k = q.get("key")
        if k:
            answers[k] = q.get("answer")

    return {
        "run_id": ((run.get("_id") or {}).get("$oid")) if isinstance(run.get("_id"), dict) else run.get("_id"),
        "name": run.get("name"),
        "game": ((run.get("game_config") or {}).get("name")),
        "player_id": run.get("player_id"),
        "source": run.get("source"),
        "exited": run.get("exited"),
        "exit_reason": run.get("exit_reason"),
        "start_ts": str(start_dt) if pd.notna(start_dt) else None,
        "end_ts": str(end_dt) if pd.notna(end_dt) else None,
        "runtime_seconds": runtime_s,
        "runtime_human": runtime_h,
        "turns_reported": run.get("turns"),
        "messages_total": n_msgs,
        "messages_human": n_human,
        "messages_ai": n_ai,
        "answers": answers,
        "feedback_count": len(run.get("feedback") or []),
    }


def load_transcripts_df(path) -> pd.DataFrame:
    """One row per message across all runs, for transcript review + turn timing stats later.
    Columns include run_id, player_id, run_name, msg_idx, speaker, content, msg_id.
    """
    path = Path(path)
    rows = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            run = json.loads(line)

            run_id = ((run.get("_id") or {}).get("$oid")) if isinstance(run.get("_id"), dict) else run.get("_id")
            player_id = run.get("player_id")
            run_name = run.get("name")
            game = (run.get("game_config") or {}).get("name")
            start_dt = parse_dt(run.get("start_ts"))
            end_dt = parse_dt(run.get("end_ts"))

            history = ((run.get("state") or {}).get("history")) or []
            for idx, msg in enumerate(history):
                speaker = msg.get("type")  # 'human' / 'ai' / etc
                content = msg.get("content")
                msg_id = msg.get("id")

                rows.append(
                    {
                        "run_id": run_id,
                        "player_id": player_id,
                        "run_name": run_name,
                        "game": game,
                        "run_start": start_dt,
                        "run_end": end_dt,
                        "msg_idx": idx,
                        "speaker": speaker,
                        "content": content,
                        "msg_id": msg_id,
                    }
                )

    df = pd.DataFrame(rows)
    # basic "time between turns" placeholder: within-run deltas based on msg order
    # (actual per-message timestamps aren't in state.history here, so this is run-level only)
    df["run_runtime_s"] = (df["run_end"] - df["run_start"]).dt.total_seconds()
    return df


def print_metadata_summary(path):
    """Print human-friendly summary of metadata.json contents (timestamps, runtimes, start/stop history)."""
    path = Path(path)

    with open(path) as f:
        data = json.load(f)

    created = data["created_at"]
    destroyed = data["destroy_time"]

    created_dt = datetime.fromtimestamp(created)
    destroyed_dt = datetime.fromtimestamp(destroyed)

    runtime = destroyed - created

    start_times = data.get("start_times", [])
    stop_times = data.get("stop_times", [])

    print("Metadata Summary")
    print("-" * 40)
    print(f"Name: {data['name']}")
    print(f"Link: {data['link']}")
    print(f"Runtime: {runtime:.2f}s ({human_duration(runtime)})")
    print()

    print("Complete run history")
    print("-" * 40)

    print(f"created/started: {created_dt}")

    for i, start in enumerate(start_times):
        start_dt = datetime.fromtimestamp(start)

        # skip first start if it equals created timestamp
        if i == 0 and abs(start - created) < 1e-6:
            pass
        else:
            print(f"started:        {start_dt}")

        if i < len(stop_times):
            stop = stop_times[i]
            stop_dt = datetime.fromtimestamp(stop)
            uptime = stop - start
            print(f"stopped:        {stop_dt}  (uptime {uptime:.2f}s / {human_duration(uptime)})")

    if destroyed_dt:
        print(f"destroyed:      {destroyed_dt}")


def load_logs(path):
    """Load one log file or all .log files in a directory into a pandas DataFrame."""
    path = Path(path)

    if path.is_file():
        files = [path]
    else:
        files = sorted(path.glob("*.log"))

    rows = []

    for log_file in files:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, start=1):
                rows.append(
                    {
                        "file": log_file.name,
                        "line_no": i,
                        "text": line.rstrip("\n"),
                    }
                )

    return pd.DataFrame(rows)


import os

import pandas as pd
import requests
from IPython.display import HTML, display

DEFAULT_MODEL = "openai/gpt-4o"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def message(
    msg,
    model=DEFAULT_MODEL,
    system_prompt=None,
    parse_response=True,
    api_key=None,
    **kwargs,
):
    """Easy wrapper to quickly send a message to an OpenRouter chat model."""
    api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENROUTER_API_KEY in environment variables.")

    # Preserve full message history if caller provides it
    if isinstance(msg, list):
        messages = list(msg)
    else:
        messages = [{"role": "user", "content": msg}]

    # Prepend system prompt if provided and not already present first
    if system_prompt is not None:
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": system_prompt}] + messages

    payload = {
        "model": model,
        "messages": messages,
        **kwargs,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    if response.status_code != 200:
        print(response.text)  # <-- shows real reason
        response.raise_for_status()
    data = response.json()

    if not parse_response:
        return data

    assistant_message = data["choices"][0]["message"]
    content = assistant_message.get("content")

    # Handle both string and structured content safely
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "".join(parts)

    return content


def display_pretty(df, max_height="400px", max_width="100%"):
    """Display DataFrame in a scrollable container with preserved line breaks."""
    table_html = df.to_html(index=False).replace("\\n", "<br>")

    html = f"""
    <div style="
        max-height: {max_height};
        max-width: {max_width};
        overflow: auto;
        border: 1px solid #ddd;
        padding: 4px;
    ">
        {table_html}
    </div>
    """

    display(HTML(html))

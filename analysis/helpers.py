"""Analysis shared helper functions."""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from IPython.display import HTML, display
from itables import show as _itables_show

DEFAULT_MODEL = "openai/gpt-4o"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def extract_feedback_per_run(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per feedback item / feedback-bearing response in runs_df.

    Includes:
    - run context: run_id, run name, player_id, timestamps
    - character context: pc / npc ids and descriptions
    - transcript: full state.history for the run
    - feedback source and content:
        * during_play_feedback from state.feedback[]
        * completion_form answers (e.g. other_feedback, user_goal_inference)
        * optional intake-form style fields if present on the row

    Expected input:
        runs_df produced from load_runs_ndjson(...), i.e. a normalized DataFrame
        where nested top-level objects become dotted columns, while arrays like
        state.history / feedback remain list-like objects.
    """
    out = []

    def _safe_get(row, col, default=None):
        return row[col] if col in row.index else default

    def _is_nonempty(x):
        if x is None:
            return False
        if isinstance(x, float) and pd.isna(x):
            return False
        if isinstance(x, str):
            return x.strip() != ""
        if isinstance(x, (list, dict, tuple, set)):
            return len(x) > 0
        return True

    def _extract_form_answers(questions):
        """Convert question entries to normalized answer objects.

            [{"key": "...", "text": "...", "answer": "..."}]
        into:
            [{"question_key": "...", "question_text": "...", "answer": "..."}]
        """
        results = []
        if not isinstance(questions, list):
            return results

        for q in questions:
            if not isinstance(q, dict):
                continue
            answer = q.get("answer")
            if _is_nonempty(answer):
                results.append(
                    {
                        "question_key": q.get("key"),
                        "question_text": q.get("text"),
                        "answer": answer,
                    }
                )
        return results

    for _, row in runs_df.iterrows():
        run_id = _safe_get(row, "_id.$oid", _safe_get(row, "_id"))
        transcript = _safe_get(row, "state.history", _safe_get(row, "history", []))

        base = {
            "run_id": run_id,
            "run_name": _safe_get(row, "name"),
            "player_id": _safe_get(row, "player_id"),
            "start_ts": _safe_get(row, "start_ts"),
            "end_ts": _safe_get(row, "end_ts"),
            "start_dt": _safe_get(row, "start_dt"),
            "end_dt": _safe_get(row, "end_dt"),
            "runtime_seconds": _safe_get(row, "runtime_seconds"),
            "runtime_human": _safe_get(row, "runtime_human"),
            "turns": _safe_get(row, "turns"),
            "exit_reason": _safe_get(row, "exit_reason", _safe_get(row, "state.exit_reason")),
            "pc_hid": _safe_get(row, "context.pc.hid"),
            "pc_description": _safe_get(row, "context.pc.short_description"),
            "npc_hid": _safe_get(row, "context.npc.hid"),
            "npc_description": _safe_get(row, "context.npc.short_description"),
            "transcript": transcript,
        }

        # 1) During-play feedback: state.feedback or top-level feedback
        raw_feedback = _safe_get(row, "feedback", _safe_get(row, "state.feedback", []))
        if isinstance(raw_feedback, list):
            for fb in raw_feedback:
                if not isinstance(fb, dict):
                    continue
                content = fb.get("content")
                if _is_nonempty(content):
                    out.append(
                        {
                            **base,
                            "feedback_source": "during_play_feedback",
                            "feedback_key": None,
                            "feedback_text": content,
                            "feedback_timestamp": fb.get("timestamp"),
                            "question_text": None,
                        }
                    )

        # 2) Completion form answers
        completion_questions = _safe_get(row, "state.forms.completion_form.questions", [])
        for item in _extract_form_answers(completion_questions):
            out.append(
                {
                    **base,
                    "feedback_source": "completion_form",
                    "feedback_key": item["question_key"],
                    "feedback_text": item["answer"],
                    "feedback_timestamp": None,
                    "question_text": item["question_text"],
                }
            )

        # 3) Optional intake / player-form text fields, if present as normalized columns
        # Adjust/add keys here if your schema evolves.
        optional_form_fields = [
            "prior_experience",
            "additional_comments",
            "user.prior_experience",
            "user.additional_comments",
        ]
        for field in optional_form_fields:
            value = _safe_get(row, field)
            if _is_nonempty(value):
                out.append(
                    {
                        **base,
                        "feedback_source": "intake_form",
                        "feedback_key": field,
                        "feedback_text": value,
                        "feedback_timestamp": None,
                        "question_text": None,
                    }
                )

    return pd.DataFrame(out)


def get_transcripts_from_runs_df(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Flatten run histories into a transcript DataFrame.

    One row per message in state.history.
    """
    if "state.history" not in runs_df.columns:
        raise ValueError("runs_df missing 'state.history' column")

    run_id_col = "_id.$oid" if "_id.$oid" in runs_df.columns else "_id"

    base_cols = [run_id_col, "player_id", "context.pc.hid", "context.npc.hid", "state.history"]
    missing = [c for c in base_cols if c not in runs_df.columns]
    if missing:
        raise ValueError(f"runs_df missing required columns: {missing}")

    df = runs_df[base_cols].copy()
    df = df.rename(
        columns={
            run_id_col: "run_id",
            "context.pc.hid": "pc",
            "context.npc.hid": "npc",
            "state.history": "history",
        }
    )

    df = df.explode("history", ignore_index=True)

    msg = pd.json_normalize(df["history"])
    df = pd.concat([df.drop(columns="history"), msg], axis=1)

    df = df.rename(
        columns={
            "type": "speaker",
            "content": "text",
        }
    )

    df["turn"] = df.groupby("run_id").cumcount() + 1

    if "timestamp" not in df.columns:
        df["timestamp"] = None

    return df[
        [
            "run_id",
            "player_id",
            "pc",
            "npc",
            "turn",
            "speaker",
            "text",
            "timestamp",
        ]
    ]


def load_logs(logs_dir: str | Path) -> pd.DataFrame:
    """Read every log file in a logs directory where each line is a JSON object.

    like:
        {"text": "...", "record": {...}}

    Returns one row per log event with flattened fields so you can inspect
    timestamps, levels, messages, file/function info, process/thread info, etc.
    """
    logs_dir = Path(logs_dir)
    rows: list[dict] = []

    for log_path in sorted(logs_dir.glob("*.log")):
        with log_path.open("r", encoding="utf-8") as f:
            for event_idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    rows.append(
                        {
                            "log_file": log_path.name,
                            "log_path": str(log_path),
                            "event_idx": event_idx,
                            "parse_error": True,
                            "raw_line": line,
                        }
                    )
                    continue

                record = obj.get("record", {}) or {}
                level = record.get("level", {}) or {}
                file_info = record.get("file", {}) or {}
                process = record.get("process", {}) or {}
                thread = record.get("thread", {}) or {}
                elapsed = record.get("elapsed", {}) or {}
                time_info = record.get("time", {}) or {}

                row = {
                    "log_file": log_path.name,
                    "log_path": str(log_path),
                    "event_idx": event_idx,
                    "parse_error": False,
                    "text": obj.get("text"),
                    "message": record.get("message"),
                    "exception": record.get("exception"),
                    "extra": record.get("extra"),
                    "function": record.get("function"),
                    "module": record.get("module"),
                    "logger_name": record.get("name"),
                    "line": record.get("line"),
                    "file_name": file_info.get("name"),
                    "file_path": file_info.get("path"),
                    "level": level.get("name"),
                    "level_no": level.get("no"),
                    "level_icon": level.get("icon"),
                    "process_id": process.get("id"),
                    "process_name": process.get("name"),
                    "thread_id": thread.get("id"),
                    "thread_name": thread.get("name"),
                    "elapsed_seconds": elapsed.get("seconds"),
                    "elapsed_repr": elapsed.get("repr"),
                    "time_repr": time_info.get("repr"),
                    "timestamp": time_info.get("timestamp"),
                }

                rows.append(row)

    logs_df = pd.DataFrame(rows)

    if logs_df.empty:
        return logs_df

    if "timestamp" in logs_df.columns:
        logs_df["timestamp"] = pd.to_datetime(logs_df["timestamp"], unit="s", utc=True, errors="coerce")

    if "time_repr" in logs_df.columns:
        parsed = pd.to_datetime(logs_df["time_repr"], utc=True, errors="coerce")
        logs_df["timestamp"] = logs_df["timestamp"].fillna(parsed)

    logs_df = logs_df.sort_values(["log_file", "event_idx"]).reset_index(drop=True)
    return logs_df


def load_players_ndjson(path) -> pd.DataFrame:
    """Load players.ndjson into a DataFrame (one row per player).

    Rules:
    - top-level scalar fields are kept as-is
    - Mongo-style {'$oid': ...} / {'$date': ...} objects are unwrapped
    - top-level form-field objects like {'key': ..., 'label': ..., 'answer': ...}
      become column -> answer
    """
    path = Path(path)
    rows = []

    def _unwrap_special(x):
        if isinstance(x, dict):
            if "$oid" in x:
                return x["$oid"]
            if "$date" in x:
                return pd.to_datetime(x["$date"], utc=True, errors="coerce")
        return x

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            player = json.loads(line)
            row = {}

            for k, v in player.items():
                # Mongo-style special values
                if isinstance(v, dict) and ("$oid" in v or "$date" in v):
                    row[k] = _unwrap_special(v)

                # Form field object: use its answer
                elif isinstance(v, dict) and "key" in v:
                    row[k] = v.get("answer")

                # Plain scalar top-level field
                else:
                    row[k] = v

            rows.append(row)

    return pd.DataFrame(rows)


def show(df: pd.DataFrame, **kwargs):
    """Helper to show a DataFrame with nice defaults for this analysis."""
    defaults = dict(
        scrollY="500px",
        scrollX=True,
        paging=True,
        pageLength=25,
        columnDefs=[{"className": "dt-left", "targets": "_all"}],
    )

    options = {**defaults, **kwargs}  # kwargs override defaults
    return _itables_show(df, **options)


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
    n_human = sum(1 for m in history if (m.get("type") == "human"))
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

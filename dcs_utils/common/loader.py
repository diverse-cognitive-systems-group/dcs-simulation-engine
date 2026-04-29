"""Load a DCS results directory into analysis-ready DataFrames.

Usage:
    from dcs_utils.common import load_all
    data = load_all("/path/to/results")
"""



import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Utility functions (inlined to avoid triggering helpers/__init__.py which
# imports itables — a Jupyter-only dependency not available in CLI context)
# ---------------------------------------------------------------------------


def _parse_dt(x):
    """Handle ISO strings and Mongo-like {'$date': ...}; return pd.Timestamp or NaT."""
    if x is None:
        return pd.NaT
    if isinstance(x, dict) and "$date" in x:
        return pd.to_datetime(x["$date"], utc=True, errors="coerce")
    if isinstance(x, str):
        return pd.to_datetime(x, utc=True, errors="coerce")
    return pd.to_datetime(x, utc=True, errors="coerce")


def _human_duration(seconds: float) -> str:
    """Convert seconds to a human-friendly string, e.g. '1h 5m 3s'."""
    from datetime import timedelta
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


def _load_logs(logs_dir: Path) -> pd.DataFrame:
    """Read every *.log file in *logs_dir* (one JSON object per line)."""
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
                    rows.append({"log_file": log_path.name, "event_idx": event_idx,
                                 "parse_error": True, "raw_line": line})
                    continue
                record = obj.get("record", {}) or {}
                level = record.get("level", {}) or {}
                file_info = record.get("file", {}) or {}
                time_info = record.get("time", {}) or {}
                rows.append({
                    "log_file":   log_path.name,
                    "event_idx":  event_idx,
                    "parse_error": False,
                    "message":    record.get("message"),
                    "exception":  record.get("exception"),
                    "function":   record.get("function"),
                    "module":     record.get("module"),
                    "line":       record.get("line"),
                    "file_name":  file_info.get("name"),
                    "level":      level.get("name"),
                    "level_no":   level.get("no"),
                    "time_repr":  time_info.get("repr"),
                    "timestamp":  time_info.get("timestamp"),
                    "text":       obj.get("text"),
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True, errors="coerce")
    if "time_repr" in df.columns:
        parsed = pd.to_datetime(df["time_repr"], utc=True, errors="coerce")
        df["timestamp"] = df["timestamp"].fillna(parsed)
    return df.sort_values(["log_file", "event_idx"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# PII columns that are always dropped from the display players DataFrame
# ---------------------------------------------------------------------------
_PII_COLS = {"email", "phone_number", "full_name"}

# ---------------------------------------------------------------------------
# Log filter settings for the errors_df
# ---------------------------------------------------------------------------
_ERROR_LEVELS = {"WARNING", "ERROR", "CRITICAL"}
_ERROR_KW_PATTERN = r"error|exception|failure|traceback|critical"


# ---------------------------------------------------------------------------
# AnalysisData
# ---------------------------------------------------------------------------


@dataclass
class AnalysisData:
    """All analysis-ready DataFrames loaded from a single results directory."""

    results_dir: Path

    # Raw metadata
    manifest: dict
    experiment: dict  # first record from experiments.json, or {}

    # Core DataFrames
    runs_df: pd.DataFrame        # sessions — one row per run
    players_df: pd.DataFrame     # players (PII columns dropped)
    transcripts_df: pd.DataFrame # session_events — one row per event
    assignments_df: pd.DataFrame # assignments — one row per assignment
    feedback_df: pd.DataFrame    # flattened form answers
    event_feedback_df: pd.DataFrame  # inline per-message feedback from session_events
    logs_df: pd.DataFrame        # log events (empty if no logs/ dir)
    characters_df: pd.DataFrame  # characters
    errors_df: pd.DataFrame      # WARNING/ERROR/CRITICAL subset of logs_df

    @property
    def runs_enriched_df(self) -> pd.DataFrame:
        """runs_df left-joined with player columns (consent_to_followup, etc.)."""
        df = self.runs_df.copy()
        if self.players_df.empty or "access_key" not in self.players_df.columns:
            return df
        optional = [c for c in ["consent_to_followup"] if c in self.players_df.columns]
        join_cols = ["access_key"] + optional
        player_sub = self.players_df[join_cols].rename(columns={"access_key": "player_id"})
        return df.merge(player_sub, on="player_id", how="left")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_all(results_dir: str | Path) -> AnalysisData:
    """Load all result files from *results_dir* into an :class:`AnalysisData`."""
    results_dir = Path(results_dir).resolve()

    manifest = _load_manifest(results_dir)
    experiment = _load_experiment(results_dir)
    runs_df = _load_runs(results_dir)
    players_df = _load_players(results_dir)
    transcripts_df = _load_transcripts(results_dir)
    assignments_df = _load_assignments(results_dir)
    feedback_df = _build_feedback(assignments_df)
    event_feedback_df = _build_event_feedback(transcripts_df, runs_df)
    characters_df = _load_characters(results_dir)
    logs_df = _load_logs_safe(results_dir)
    errors_df = _filter_errors(logs_df)

    return AnalysisData(
        results_dir=results_dir,
        manifest=manifest,
        experiment=experiment,
        runs_df=runs_df,
        players_df=players_df,
        transcripts_df=transcripts_df,
        assignments_df=assignments_df,
        feedback_df=feedback_df,
        event_feedback_df=event_feedback_df,
        logs_df=logs_df,
        characters_df=characters_df,
        errors_df=errors_df,
    )


# ---------------------------------------------------------------------------
# Private loaders
# ---------------------------------------------------------------------------


def _load_json_array(path: Path) -> list[dict]:
    """Return a JSON array from *path*, or [] if the file is missing."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def _unwrap_oid(value) -> str | None:
    """Unwrap a Mongo {"$oid": "..."} to a plain string."""
    if isinstance(value, dict) and "$oid" in value:
        return value["$oid"]
    return value


def _unwrap_mongo(obj):
    """Recursively unwrap Mongo extended-JSON special values in a dict/list.

    {"$oid": "..."} → plain str
    {"$date": "..."} → ISO string (kept as str so json_normalize keeps it flat)

    This must run *before* pd.json_normalize so that timestamp fields become
    simple strings (not nested dicts that normalize expands into dotted columns).
    """
    if isinstance(obj, dict):
        if "$oid" in obj:
            return obj["$oid"]
        if "$date" in obj:
            # Return the ISO string; _parse_dt will convert it later
            return obj["$date"]
        return {k: _unwrap_mongo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unwrap_mongo(i) for i in obj]
    return obj


def _load_manifest(results_dir: Path) -> dict:
    p = results_dir / "__manifest__.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _load_experiment(results_dir: Path) -> dict:
    records = _load_json_array(results_dir / "experiments.json")
    if not records:
        return {}
    exp = records[0]
    # Unwrap _id
    exp["_id"] = _unwrap_oid(exp.get("_id"))
    return exp


def _load_runs(results_dir: Path) -> pd.DataFrame:
    records = _load_json_array(results_dir / "sessions.json")
    if not records:
        return pd.DataFrame()

    records = [_unwrap_mongo(r) for r in records]
    df = pd.json_normalize(records, sep=".")

    # Parse timestamps
    for col in ["session_started_at", "session_ended_at", "created_at", "updated_at"]:
        if col in df.columns:
            df[col] = df[col].apply(_parse_dt)

    # Derived columns
    if "session_started_at" in df.columns and "session_ended_at" in df.columns:
        df["duration_minutes"] = (
            (df["session_ended_at"] - df["session_started_at"])
            .dt.total_seconds()
            .div(60)
            .round(2)
        )
        df["duration_human"] = df["duration_minutes"].apply(
            lambda m: _human_duration(m * 60) if pd.notna(m) else "—"
        )
    else:
        df["duration_minutes"] = pd.NA
        df["duration_human"] = "—"

    pc = df["pc_hid"].astype(str) if "pc_hid" in df.columns else "?"
    npc = df["npc_hid"].astype(str) if "npc_hid" in df.columns else "?"
    df["pairing"] = pc + " → " + npc

    return df


def _unwrap_player_field(key: str, value) -> object:
    """Unwrap a player form-field dict to its answer value (or the raw value)."""
    if isinstance(value, dict):
        if "$oid" in value:
            return value["$oid"]
        if "$date" in value:
            return _parse_dt(value)
        if "key" in value:
            # Form field object — use answer if present
            answer = value.get("answer")
            if isinstance(answer, list):
                return "; ".join(str(a) for a in answer)
            return answer
    return value


def _load_players(results_dir: Path) -> pd.DataFrame:
    records = _load_json_array(results_dir / "players.json")
    if not records:
        return pd.DataFrame()

    rows = []
    for player in records:
        row = {}
        for k, v in player.items():
            row[k] = _unwrap_player_field(k, v)
        rows.append(row)

    df = pd.DataFrame(rows)

    # Drop raw PII columns
    drop = [c for c in _PII_COLS if c in df.columns]
    df = df.drop(columns=drop)

    return df


def _load_transcripts(results_dir: Path) -> pd.DataFrame:
    records = _load_json_array(results_dir / "session_events.json")
    if not records:
        return pd.DataFrame()

    records = [_unwrap_mongo(r) for r in records]
    df = pd.json_normalize(records, sep=".")

    for col in ["event_ts", "persisted_at"]:
        if col in df.columns:
            df[col] = df[col].apply(_parse_dt)

    return df


def _load_assignments(results_dir: Path) -> pd.DataFrame:
    records = _load_json_array(results_dir / "assignments.json")
    if not records:
        return pd.DataFrame()

    records = [_unwrap_mongo(r) for r in records]
    df = pd.json_normalize(records, sep=".")

    for col in ["assigned_at", "started_at", "completed_at", "created_at", "updated_at"]:
        if col in df.columns:
            df[col] = df[col].apply(_parse_dt)

    return df


def _build_feedback(assignments_df: pd.DataFrame) -> pd.DataFrame:
    """Flatten assignment form_responses into one row per answered question."""
    if assignments_df.empty or "form_responses" not in assignments_df.columns:
        return pd.DataFrame()

    rows = []
    for _, row in assignments_df.iterrows():
        responses = row.get("form_responses")
        if not isinstance(responses, dict):
            continue
        for form_name, form_data in responses.items():
            if not isinstance(form_data, dict):
                continue
            answers = form_data.get("answers") or {}
            submitted_at = _parse_dt(form_data.get("submitted_at"))
            for key, ans_obj in answers.items():
                if not isinstance(ans_obj, dict):
                    continue
                answer = ans_obj.get("answer")
                if answer is None or str(answer).strip() == "":
                    continue
                if isinstance(answer, list):
                    answer = "; ".join(str(a) for a in answer)
                trigger = form_data.get("trigger")
                trigger_event = trigger.get("event") if isinstance(trigger, dict) else None
                rows.append({
                    "player_id":       row.get("player_id"),
                    "game_name":       row.get("game_name"),
                    "experiment_name": row.get("experiment_name"),
                    "form_name":       form_name,
                    "trigger_event":   trigger_event,
                    "submitted_at":    submitted_at,
                    "question_key":    key,
                    "question_prompt": ans_obj.get("prompt"),
                    "answer_type":     ans_obj.get("answer_type"),
                    "answer":          answer,
                })

    return pd.DataFrame(rows)


def _build_event_feedback(transcripts_df: pd.DataFrame, runs_df: pd.DataFrame) -> pd.DataFrame:
    """Extract inline per-message feedback from session_events into one row per feedback."""
    if transcripts_df.empty or "feedback.liked" not in transcripts_df.columns:
        return pd.DataFrame()

    mask = transcripts_df["feedback.liked"].notna()
    df = transcripts_df[mask].copy()
    if df.empty:
        return pd.DataFrame()

    # Join game_name and player_id from sessions
    if not runs_df.empty and "session_id" in runs_df.columns:
        session_meta = runs_df[
            [c for c in ["session_id", "game_name", "player_id"] if c in runs_df.columns]
        ]
        df = df.merge(session_meta, on="session_id", how="left")

    flags = []
    for col, label in [
        ("feedback.doesnt_make_sense", "doesn't make sense"),
        ("feedback.out_of_character", "out of character"),
        ("feedback.other", "other"),
    ]:
        if col in df.columns:
            flags.append((col, label))

    rows = []
    for _, row in df.iterrows():
        liked = row.get("feedback.liked")
        comment = str(row.get("feedback.comment") or "").strip()
        active_flags = [label for col, label in flags if row.get(col)]
        rows.append({
            "session_id":   row.get("session_id"),
            "game_name":    row.get("game_name"),
            "player_id":    row.get("player_id"),
            "seq":          row.get("seq"),
            "turn_index":   row.get("turn_index"),
            "liked":        liked,
            "flags":        ", ".join(active_flags) if active_flags else "",
            "comment":      comment,
            "submitted_at": _parse_dt(row.get("feedback.submitted_at")),
        })

    return pd.DataFrame(rows)


def _load_characters(results_dir: Path) -> pd.DataFrame:
    records = _load_json_array(results_dir / "characters.json")
    if not records:
        return pd.DataFrame()
    records = [_unwrap_mongo(r) for r in records]
    return pd.json_normalize(records, sep=".")


def _load_logs_safe(results_dir: Path) -> pd.DataFrame:
    logs_dir = results_dir / "logs"
    if not logs_dir.is_dir():
        return pd.DataFrame()
    try:
        return _load_logs(logs_dir)
    except Exception:
        return pd.DataFrame()


def _filter_errors(logs_df: pd.DataFrame) -> pd.DataFrame:
    if logs_df.empty or "level" not in logs_df.columns:
        return pd.DataFrame()
    level_mask = logs_df["level"].isin(_ERROR_LEVELS)
    msg_mask = (
        logs_df["message"].str.contains(_ERROR_KW_PATTERN, case=False, na=False)
        if "message" in logs_df.columns
        else pd.Series(False, index=logs_df.index)
    )
    return logs_df[level_mask | msg_mask].reset_index(drop=True)

"""Display the conversation paths explored in a character evaluation."""

from collections import defaultdict
from pathlib import Path

from dcs_simulation_engine.hitl.evaluation import transcript_parts
from dcs_simulation_engine.reporting.loader import AnalysisData
from dcs_simulation_engine.reporting.semantic_diversity import semantic_diversity
from jinja2 import Environment, FileSystemLoader


def render(data: AnalysisData) -> str:
    sessions = data.runs_df
    if "evaluator_description" not in sessions or sessions.empty:
        return '<p class="text-muted">No evaluation paths available for this character.</p>'

    sessions = sessions[sessions["evaluator_description"].notna()].fillna("").to_dict("records")
    roots = []
    forks = defaultdict(list)
    for session in sessions:
        session["type"] = "branch"
        if parent := session.get("branch_from_session_id"):
            forks[parent, int(session["branch_from_seq"])].append(session)
        else:
            roots.append(session)

    events = defaultdict(list)
    if not data.transcripts_df.empty:
        for event in data.transcripts_df.sort_values("seq").fillna("").to_dict("records"):
            events[event["session_id"]].append(event)

    for session in sessions:
        session_id = session["session_id"]
        transcript = list(forks[session_id, 0])
        for event in events[session_id]:
            transcript.append({
                **event,
                "type": event["event_type"],
                "source": "pc" if event["event_source"] == "user" else event["event_source"],
            })
            transcript.extend(forks[session_id, event["seq"]])
        session["parts"] = transcript_parts(transcript, opening=not session.get("branch_from_session_id"))

    template = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    ).get_template("quality_coverage.html")
    metrics, model_notice = semantic_diversity(roots)
    return template.render(roots=roots, metrics=metrics, model_notice=model_notice)

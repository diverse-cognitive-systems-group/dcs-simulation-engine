"""Section 8 — Players.

PII-safe player records DataTable. Raw PII columns (email, phone_number,
full_name) are already stripped from players_df by the loader.
Run count is added by joining against runs_df.
"""

from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

_RENAME = {
    "access_key": "Access Key",
    "consent_to_followup": "Consent to Follow-up",
    "consent_signature": "Consent Signature",
    "access_key_revoked": "Revoked",
    "created_at": "Created At",
    "last_key_issued_at": "Last Key Issued",
    "run_count": "Runs",
}


def render(data: AnalysisData) -> str:
    df = data.players_df.copy()

    if df.empty:
        return '<div class="alert alert-info">No player records found.</div>'

    # Add run count
    if not data.runs_df.empty and "player_id" in data.runs_df.columns:
        run_counts = data.runs_df.groupby("player_id").size().reset_index(name="run_count")
        if "access_key" in df.columns:
            df = df.merge(
                run_counts.rename(columns={"player_id": "access_key"}),
                on="access_key",
                how="left",
            )
        df["run_count"] = df.get("run_count", 0).fillna(0).astype(int)

    # Drop internal _id column for display
    display = df.drop(columns=["_id"], errors="ignore")

    rename = {k: v for k, v in _RENAME.items() if k in display.columns}

    return df_to_datatable(
        display,
        table_id="players-table",
        rename=rename,
        truncate_cols=["consent_to_followup", "consent_signature"],
        truncate_at=120,
    )

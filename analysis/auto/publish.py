"""Publish utilities for dcs-utils.

Provides pure functions for:
- Parsing the per-NPC simulation quality table from a report HTML
- Building CharacterRecord from a characters.json document
- Loading / saving JSON seed files
"""

import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


# ---------------------------------------------------------------------------
# HTML table parser
# ---------------------------------------------------------------------------

class _TableParser(HTMLParser):
    """Extract rows from a <table id="..."> element."""

    def __init__(self, table_id: str) -> None:
        super().__init__()
        self._target_id = table_id
        self._in_target = False
        self._in_thead = False
        self._in_tbody = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self.headers: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "table" and attr_dict.get("id") == self._target_id:
            self._in_target = True
        if not self._in_target:
            return
        if tag == "thead":
            self._in_thead = True
        elif tag == "tbody":
            self._in_tbody = True
        elif tag in ("th", "td"):
            self._in_cell = True
            self._current_cell = []
        elif tag == "tr" and (self._in_thead or self._in_tbody):
            self._current_row = []

    def handle_endtag(self, tag: str) -> None:
        if not self._in_target:
            return
        if tag == "table":
            self._in_target = False
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag in ("th", "td"):
            cell_text = "".join(self._current_cell).strip()
            self._current_row.append(cell_text)
            self._in_cell = False
        elif tag == "tr":
            if self._in_thead and self._current_row:
                # may be the filter row (empty cells) — keep first non-empty header row
                if any(c for c in self._current_row) and not self.headers:
                    self.headers = list(self._current_row)
            elif self._in_tbody and self._current_row:
                self.rows.append(list(self._current_row))

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)

    def handle_entityref(self, name: str) -> None:
        _entities = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "nbsp": " "}
        if self._in_cell:
            self._current_cell.append(_entities.get(name, ""))

    def handle_charref(self, name: str) -> None:
        if self._in_cell:
            try:
                ch = chr(int(name[1:], 16) if name.startswith("x") else int(name))
                self._current_cell.append(ch)
            except (ValueError, OverflowError):
                pass


def parse_sim_quality_table(html: str) -> list[dict[str, Any]]:
    """Parse the per-NPC simulation quality table from a report HTML string.

    Returns a list of dicts, one per NPC character::

        [{"npc_hid": "NA", "turns": 25, "icf": 0.96, "dms": 0.01}, ...]

    Raises
    ------
    ValueError
        If the table ``sim-quality-per-npc-table`` is not found in the HTML.
        This means the report was generated before the simulation_quality section
        was added. Regenerate with::

            dcs-utils generate report ... --template simulation_quality
    """
    parser = _TableParser("sim-quality-per-npc-table")
    parser.feed(html)

    if not parser.headers:
        raise ValueError(
            "Report has no simulation quality per-NPC table "
            "('sim-quality-per-npc-table' not found). "
            "Regenerate the report with: "
            "dcs-utils generate report <results_dir> --template simulation_quality"
        )

    # Normalise header names → column indices
    headers_lower = [h.strip().lower() for h in parser.headers]

    def _col(name: str) -> int:
        try:
            return headers_lower.index(name)
        except ValueError:
            raise ValueError(
                f"Expected column {name!r} in sim-quality-per-npc-table "
                f"but found: {parser.headers}"
            )

    npc_col   = _col("hid")
    turns_col = _col("turns")
    icf_col   = _col("icf")
    nco_col   = _col("nco")

    def _pct(s: str) -> float:
        """Convert '96.0%' → 0.96, '—' → 0.0."""
        s = s.strip()
        if s in ("—", "-", ""):
            return 0.0
        return round(float(s.rstrip("%")) / 100, 6)

    results: list[dict[str, Any]] = []
    for row in parser.rows:
        if len(row) <= max(npc_col, turns_col, icf_col, nco_col):
            continue
        npc_hid = row[npc_col].strip()
        if not npc_hid:
            continue
        try:
            turns = int(row[turns_col].strip())
        except ValueError:
            turns = 0
        results.append({
            "npc_hid": npc_hid,
            "turns":   turns,
            "icf":     _pct(row[icf_col]),
            "dms":     _pct(row[nco_col]),
        })

    return results


# ---------------------------------------------------------------------------
# CharacterRecord builder
# ---------------------------------------------------------------------------

_CHAR_RECORD_KNOWN_FIELDS = {"hid", "name", "short_description"}


def build_char_record_from_doc(doc: dict[str, Any]) -> CharacterRecord:
    """Build a :class:`CharacterRecord` from a characters.json document."""
    return CharacterRecord(
        hid=doc["hid"],
        name=doc.get("name", ""),
        short_description=doc.get("short_description", ""),
        data={k: v for k, v in doc.items() if k not in _CHAR_RECORD_KNOWN_FIELDS},
    )


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def load_json_file(path: Path) -> list | dict:
    """Read and return parsed JSON from *path*."""
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_file(path: Path, data: list | dict) -> None:
    """Write *data* as formatted JSON to *path* (2-space indent, trailing newline)."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

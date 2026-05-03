"""Character coverage report — metadata section.

Renders a Bootstrap card showing total character count, human/non-human
breakdown, and the list of character keys (HIDs), using the same dl-meta
style as the default metadata section.
"""

import json
from pathlib import Path


def render(repo_root: Path, hids_filter: list[str] | None = None, db: str = "prod") -> str:
    chars_path = repo_root / "database_seeds" / db / "characters.json"
    chars_raw: list[dict] = json.loads(chars_path.read_text(encoding="utf-8"))

    if hids_filter:
        chars_raw = [c for c in chars_raw if c["hid"] in hids_filter]

    human = [c for c in chars_raw if c.get("is_human")]
    nonhuman = [c for c in chars_raw if not c.get("is_human")]
    total = len(chars_raw)

    hids_html = ", ".join(f"<code>{c['hid']}</code>" for c in chars_raw)

    rows = [
        ("Total Characters", str(total)),
        ("Human", str(len(human))),
        ("Non-human", str(len(nonhuman))),
        ("Keys", hids_html),
    ]

    dl_items = "".join(f"<dt class='col-sm-3'>{label}</dt><dd class='col-sm-9'>{value}</dd>" for label, value in rows)

    return f"""
<div class="card">
  <div class="card-body">
    <dl class="row dl-meta mb-0">
      {dl_items}
    </dl>
  </div>
</div>
"""

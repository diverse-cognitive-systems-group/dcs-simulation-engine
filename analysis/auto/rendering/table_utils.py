"""DataFrame → DataTables HTML rendering.

df_to_datatable(df, table_id, ...) returns a self-contained HTML string
containing a <table> and a <script> block that initialises the DataTables
plugin for that table. The page must load jQuery, DataTables core, and the
DataTables Bootstrap 5 + Buttons plugins from CDN.
"""

from __future__ import annotations

import html as _html

import pandas as pd


def df_to_datatable(
    df: pd.DataFrame,
    table_id: str,
    columns: list[str] | None = None,
    rename: dict[str, str] | None = None,
    page_length: int = 25,
    scroll_x: bool = True,
    export_buttons: bool = True,
    truncate_cols: list[str] | None = None,
    truncate_at: int = 400,
) -> str:
    """Render *df* as a Bootstrap 5 DataTable HTML string.

    Parameters
    ----------
    df:
        Source DataFrame.
    table_id:
        HTML id attribute for the <table> (must be unique in the page).
    columns:
        Subset and order of columns to include. All columns used if None.
    rename:
        Optional {source_col: display_name} map applied after column selection.
    page_length:
        Rows shown per page.
    scroll_x:
        Enable horizontal scrolling.
    export_buttons:
        Include Copy / CSV / Excel / Column-visibility buttons.
    truncate_cols:
        Column names whose display values should be truncated to *truncate_at*
        chars with the full text in a `title` attribute.
    truncate_at:
        Character limit for truncated columns (default 400).
    """
    display = df[columns].copy() if columns else df.copy()
    if rename:
        display = display.rename(columns=rename)

    # Convert timestamps to ISO strings for readability
    for col in display.select_dtypes(include=["datetimetz", "datetime64[ns, UTC]", "datetime"]).columns:
        display[col] = display[col].dt.strftime("%Y-%m-%d %H:%M:%S UTC").where(display[col].notna(), "")

    # Replace NaN/NaT with empty string for clean display
    display = display.fillna("")

    # Build <table> HTML
    table_html = display.to_html(
        table_id=table_id,
        classes="table table-striped table-hover table-sm w-100",
        border=0,
        index=False,
        escape=True,
    )

    # Apply truncation post-render by patching cell content (simple approach:
    # re-render with truncated values but title containing original)
    if truncate_cols:
        display_trunc = display.copy()
        for col in truncate_cols:
            if col not in display_trunc.columns:
                continue
            disp_col = rename.get(col, col) if rename else col
            if disp_col not in display_trunc.columns:
                continue
            def _trunc(val, limit=truncate_at):
                s = str(val)
                if len(s) <= limit:
                    return s
                escaped_full = _html.escape(s, quote=True)
                escaped_short = _html.escape(s[:limit], quote=True)
                return f'<span title="{escaped_full}">{escaped_short}…</span>'

            display_trunc[disp_col] = display_trunc[disp_col].apply(_trunc)

        table_html = display_trunc.to_html(
            table_id=table_id,
            classes="table table-striped table-hover table-sm w-100",
            border=0,
            index=False,
            escape=False,
        )

    # Build DataTables init <script>
    dom = "Bfrtip" if export_buttons else "frtip"
    buttons_js = (
        """buttons: ['copy', 'csv', 'excel', 'colvis'],"""
        if export_buttons
        else ""
    )
    scroll_js = "true" if scroll_x else "false"

    script = f"""
<script>
$(document).ready(function () {{
    $('#{table_id}').DataTable({{
        pageLength: {page_length},
        scrollX: {scroll_js},
        dom: '{dom}',
        {buttons_js}
        order: [],
    }});
}});
</script>"""

    return table_html + "\n" + script

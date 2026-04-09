"""DataFrame → DataTables HTML rendering.

df_to_datatable(df, table_id, ...) returns a self-contained HTML string
containing a <table> and a <script> block that initialises the DataTables
plugin for that table. The page must load jQuery, DataTables core, and the
DataTables Bootstrap 5 + Buttons plugins from CDN (all in <head>).
"""



import html as _html

import pandas as pd


def df_to_datatable(
    df: pd.DataFrame,
    table_id: str,
    columns: list[str] | None = None,
    rename: dict[str, str] | None = None,
    scroll_y: str = "400px",
    scroll_x: bool = True,
    export_buttons: bool = True,
    truncate_cols: list[str] | None = None,
    truncate_at: int = 400,
    column_filters: bool = True,
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
    scroll_y:
        Max height of the table body before vertical scrolling kicks in.
        Set to "" to disable (falls back to pagination). Default "400px".
    scroll_x:
        Enable horizontal scrolling.
    export_buttons:
        Include Copy / CSV / Excel / Column-visibility buttons.
    truncate_cols:
        Column names whose display values should be truncated to *truncate_at*
        chars with the full text in a `title` attribute.
    truncate_at:
        Character limit for truncated columns (default 400).
    column_filters:
        Add per-column search inputs in a second header row (default True).
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

    # Inject a second <tr> in <thead> for per-column filter inputs.
    # Using the header (not footer) avoids scrollX null-return issues.
    if column_filters:
        n_cols = len(display.columns)
        filter_cells = "".join("<th></th>" for _ in range(n_cols))
        filter_row = f'<tr class="dt-filter-row">{filter_cells}</tr>'
        table_html = table_html.replace("</thead>", f"{filter_row}\n</thead>", 1)

    use_scroll_y = bool(scroll_y)

    # Bootstrap 5 DataTables DOM layout.
    # When scrollY is active, pagination is replaced by vertical scrolling
    # so 'p' (pagination) and 'l' (length menu) are dropped from the dom.
    if use_scroll_y:
        dom = (
            "<'row align-items-center mb-2'<'col-auto'f><'col d-flex justify-content-end'B>>"
            "<'row'<'col-sm-12'tr>>"
            "<'row mt-2'<'col-sm-12'i>>"
        )
    else:
        dom = (
            "<'row align-items-center mb-2'<'col-auto'f><'col d-flex justify-content-end'B>>"
            "<'row'<'col-sm-12'tr>>"
            "<'row mt-2'<'col-sm-12 col-md-5'i><'col-sm-12 col-md-7'p>>"
        )

    buttons_js = (
        """buttons: {
            buttons: ['copy', 'csv', 'excel', 'colvis'],
            dom: { button: { className: 'btn btn-outline-secondary btn-sm' } }
        },"""
        if export_buttons else ""
    )
    scroll_x_js = "true" if scroll_x else "false"
    scroll_y_js = f'scrollY: "{scroll_y}", scrollCollapse: true, paging: false,' if use_scroll_y else "pageLength: 10, lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'All']],"

    col_filter_js = ""
    if column_filters:
        col_filter_js = f"""
        orderCellsTop: true,
        initComplete: function () {{
            var api = this.api();
            var wrapper = $('#{table_id}').closest('.dataTables_wrapper');
            api.columns().every(function () {{
                var col = this;
                var filterTh = wrapper.find('.dataTables_scrollHead thead tr.dt-filter-row th').eq(col.index());
                $('<input type="text" placeholder="Filter\u2026" class="form-control form-control-sm"/>')
                    .appendTo(filterTh.empty())
                    .on('input', function () {{ col.search(this.value).draw(); }});
            }});
        }},"""

    script = f"""
<script>
$(document).ready(function () {{
    $('#{table_id}').DataTable({{
        {scroll_y_js}
        scrollX: {scroll_x_js},
        dom: "{dom}",
        {buttons_js}
        order: [],{col_filter_js}
    }});
}});
</script>"""

    return table_html + "\n" + script

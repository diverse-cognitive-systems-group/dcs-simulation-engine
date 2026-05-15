# Analyze Results

Run results are database exports that include gameplay sessions, events, player metadata, form responses, logs, and run metadata. You can generate an HTML report from any exported results directory.

## Export Local Results

Dump the local database into a timestamped directory under `runs/`:

```sh
dcs database dump runs
```

Then stop the local engine when you are done:

```sh
dcs engine stop
```

## Export Remote Results

Download results while keeping the remote deployment running:

```sh
dcs remote save --uri <remote_api_url> --admin-key <admin_key> --save-db-path runs/<run_results>.tar.gz
```

Or save results and destroy the remote Fly apps:

```sh
dcs remote stop \
  --uri <remote_api_url> \
  --admin-key <admin_key> \
  --save-db-path runs/<run_results>.tar.gz \
  --api-app <api_app> \
  --ui-app <ui_app> \
  --db-app <db_app>
```

If `DCS_ADMIN_KEY` is set in your environment, you can omit `--admin-key`.

## Generate a Report

Generate the default HTML report:

```sh
dcs report results runs/<path_to_dumped_run_results>
```

By default, reports are written to `reports/`. To choose the output path:

```sh
dcs report results runs/<path_to_dumped_run_results> --report-path reports/my-report.html
```

Useful report options:

- `--open` opens the report in your browser after generation
- `--only <section>` renders only selected sections
- `--include <section>` adds sections to the default report
- `--exclude <section>` removes sections from the default report

For deeper analysis, use the exported JSON files directly in your own notebooks or scripts.

# Play and Monitor

After the engine is running, players use the web UI (human players) or API (AI players) while operators monitor the run from the CLI.

## Monitor a Local Run

To monitor the status of a local run, use:

```sh
dcs engine status
```

For deeper inspection during a run, dump the database to a timestamped results directory:

```sh
dcs database dump runs
```

## Monitor a Remote Run

To monitor the status of a remote run, use:

```sh
dcs remote status --uri <remote_api_url> --admin-key <admin_key>
```

If `DCS_ADMIN_KEY` is set in your environment, you can omit `--admin-key`.

To download remote results while keeping the deployment running:

```sh
dcs remote save --uri <remote_api_url> --admin-key <admin_key> --save-db-path runs/<run_results>.tar.gz
```

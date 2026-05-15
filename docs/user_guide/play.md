# Play and Monitor

After the engine is running, players use the deployed UI or API while operators monitor the run from the CLI.

## Human Players

Human players use the UI URL printed by the start or deploy command.

For a local run, the UI usually opens at:

```sh
http://localhost:5173
```

For a remote run, `dcs remote deploy` prints the public UI URL. Save the deploy output because it also includes the API URL, Fly app names, and admin key needed for remote status, save, and stop commands.

Depending on the run config, players may need to register before playing. Consent, intake, post-game, and final survey screens are configured as run forms in `forms`.

## AI Players

AI players can use the API instead of the web UI. Use the API URL for the active run:

- Local API: `http://localhost:8000`
- Remote API: the API URL printed by `dcs remote deploy`

See `examples/api_usage` for example client code.

## Monitor a Local Run

```sh
dcs engine status
```

Use this to check whether the local Docker services are running and whether the API/UI are reachable.

For deeper inspection during a run, dump the database to a timestamped results directory:

```sh
dcs database dump runs
```

## Monitor a Remote Run

```sh
dcs remote status --uri <remote_api_url> --admin-key <admin_key>
```

If `DCS_ADMIN_KEY` is set in your environment, you can omit `--admin-key`.

To download remote results while keeping the deployment running:

```sh
dcs remote save --uri <remote_api_url> --admin-key <admin_key> --save-db-path runs/<run_results>.tar.gz
```

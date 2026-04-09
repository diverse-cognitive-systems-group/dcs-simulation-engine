# Advanced Usage

TODO: add using the engine with other frontends
TOOD: add deploying to other providers (not Fly.io)
TODO: adding/extending characters and games
TODO: benchmarking custom models
TODO: use the API directly (non-run harness)


## Custom Characters

**1. Develop and Test**

- Create or modify a character sheet based on research (e.g., primary source materials, interviews with experts, etc.)
- Add it to database (`database_seeds/dev/characters.json`)
- Run simulations and observe behavior using live engine or human in the loop testing process (see `dcs-utils admin hitl --help` for details on how to run hitl tests)

**2. Evaluate Fidelity**
- Flag character behavior that doesn't align with expectations (e.g., "Out of Character" flags)
- Iterate until the character meets an in-character fidelity (ICF) threshold across scenarios

**3. Generate Report**

Generate a character quality report using:

```sh
dcs generate report <path/to/results> --include sim-quality --title "Simulation Quality Report"
```

Example quality reports are includes in the `examples/` directory of the main repo.

**4. Publish for Review**

Publish the character quality report using:

```sh
dcs publish report character_quality <path/to/results>
```

Or manually update the following:
- Add results to `character_evaluations.json`
- Add report to `docs/design/simulation_quality`
- Add character to `database_seeds/prod/characters.json`    

Then open a PR for peer review of the character.

## Custom Games

To build custom games, checkout the code (see the contributing guide in the main repo for instructions).

1. **Implement the game interface** by creating a new game file (e.g. `dcs_simulation_engine/games/new-game.py`) and implementing the required methods.

2. **Add the game to your run config** (see `examples/run_configs` for examples)

3. **Run it** locally to test it manually and/or add tests in `tests/` to validate the game flow logic. Then run it remotely to share with others (see the user guide for run and deployment instructions).
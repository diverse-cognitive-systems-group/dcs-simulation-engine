# Contributing Guidelines

Fork the repo and submit a PR with your changes. 

*(No specific format is required for PRs at this point...as long as its reasonable/understandble and focuses on the core development areas needed (discussed below) it will be considered.)*

## Creating new characters

To create a new character, follow these steps:
1. Add the character definition to the `database_seeds/characters.json` file. Use existing character entries as examples.
2. ...

## Creating new experiments/games

To create a new game/experiment configuration:

1. Create a new yaml file in the `games` directory, e.g. `games/new-game-name.yml`.
2. Define the game parameters, characters, and settings in the yaml file using the existing game files as guides or the GameConfig class definition.
3. ...
4. (optional) Launch your new game using ....

## Contributing to Core Codebase

To update the simulation engine itself 

### Launch game

*Note: Our demo deployments use Fly.io for hosting the demo Gradio widget and demo API. We update these using github actions when we push to main branch.*

After testing locally, you can launch your game using your local machine with Gradio public link sharing or deploy to GCP.

#### Pre-pilot test using Gradio public link on your local machine:

If you are just sharing with a few folks for pilot testing you can launch the widget locally with Gradio's share option like this. It will output a temporary public link you can share with others to access your local instance.

```bash
python scripts/run_widget.py --game Explore --share
```

#### Launching an experiment (using Fly.io):

1. Setup 

```bash
# either use the gui or command line, here is command line way

# install if you don't have it already
brew install flyctl
# signup or login
fly auth signup
fly auth login

# initialize fly app (only need to do this once)
fly launch --no-deploy

# deploy to fly
fly deploy

# view deployed app in browser
fly apps open
```

## General Contributing Workflow

### 1) Fork the repo (or clone if you have write access)
[Here are some instructions](https://docs.github.com/en/get-started/quickstart/fork-a-repo) on how to do that if you are unfamiliar

### 2) Start docker daemon
Dev container is configured to run docker so it will throw an error if you try to launch the dev container before starting the docker daemon. To launch either run docker gui or run ```docker info``` in terminal

### 3) Launch dev container
From VS-code make sure you have the [DevContainers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension intalled then launch the dev container like this or by clicking the green button in the bottom left of the VS-code window
![launch dev container](images/launch_dev_container.png)

At this point all dev dependencies have been installed and you can start running code, tests, making changes, etc.

### 4) Contribute
Probably wise to start by running unit tests to wrap your head around how things work and are called and unitized. But do whatever suits your fancy.

For example, now your terminal in VS-code will be running in the dev container so you can make sure poetry successfully installed all deps by running ```poetry show``` in the terminal

```sh
# NOTE: you prob need to run poetry install so that dcs_simulation_engine is aviable in ipython and in tests scripts 
poetry install
```

![terminal in dev container](images/terminal_in_container.png)

OR you can launch ipython by running ```ipython``` in the terminal

![ipython usage](images/ipython_usage.png)

OR you can run unit tests like this

Note: if dev.Dockerfile include --no-root you may need to install local package "poetry install" to make dcs_simulation_engine avaiable in tests

#### Example runs

```sh
# runs a pytest (stops at first failure, shows print statements)
poetry run pytest tests/test_utils.py -x -s

# runs a specific unit test within a module/file
poetry run pytest tests/test_utils::test_specific_thing

# runs the cli help to see available commands
poetry run python scripts/run_cli.py --help
```

![pytest usage](images/pytest_usage.png)
or all tests
![pytest all unit tests](images/unit_tests.png)

OR you can run any of the scripts by typing copi (tab completion to get the copilot-bla scripts)

![scripts](images/copilot_scripts.png)

Running the `run_cli` script looks like this 
![run_cli](images/run_cli.png)

and outputs TODO

#### Run API

```sh
uvicorn dcs_simulation_engine.api.main:app --reload
```

### 5) Submit PR
Once you are done making changes and want to submit a PR you can do so by clicking the "create pull request" button in the github UI


# Troublshooting and Additional Gotchas you may run into

- If you are contributing to .ipynb notebooks you need to run `nbstripout --install` so that no nb output is committed

⸻

Thank you for contributing!
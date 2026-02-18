# Contributing Guidelines

Contributing involves forking the repo (or cloning it if you have write access, such as being part of the DCS group/org) and submitting a PR with your changes.

Internally DCS group works on issues, features, etc. according to the [DCS project](https://github.com/orgs/diverse-cognitive-systems-group/projects/1)

*No specific format is required for PRs at this point...as long as its reasonable/understandble and focuses on the core development areas needed (discussed below) it will be considered.*

## Step by Step Contributing Guide

### 1) Fork the repo (or clone if you have write access)
DCS group members should clone the repo directly.

You should now see the code on your local machine. If you are not sure, open a terminal and type:

```sh
pwd && test -d dcs_simulation_engine && echo "Folder structure looks correct" || echo "Folder structure is incorrect"
```
*Note: this command will only work on Mac/Linux*

### 2) Python Setup

It is recommended that you use [uv](https://github.com/astral-sh/uv) to manage your Python environment.

```sh
# install uv (if you don't have it already)
pip install uv

# install python 3.13 with uv
uv python install 3.13

# create a new virtual environment with uv
uv venv --python 3.13

# activate the virtual environment
source .venv/bin/activate

# install dependencies and install your current project in editable mode
uv sync --extra dev
```

### 3) Add .env file
Create a .env file in the root of the project. (Just copy the .env.example file and rename it to .env then add your access keys for MongoDB, OpenRouter, etc.)

```sh
# Command to copy example env file to .env if you'd rather do it from terminal instead of manually in explorer.
cp .env.example .env
```

*Make sure you add your access keys (DCS group members can DM group admin for these)*

### 4) Docker Setup

To run the engine locally, you will need to have Docker installed and running on your machine. You can download Docker Desktop from [docker.com](https://www.docker.com/get-started/).

### 5) Verify Setup

To verify everything is working, run the functional tests:

```sh
uv run pytest -m functional
```

You can also run the Explore game locally:

```sh
# run the Explore game using the CLI interface
uv run python scripts/run_cli.py --game Explore
# type /quit or /exit to exit the game; /help for help

# run the Explore game using the WIDGET interface
uv run python scripts/run_widget.py --game Explore
# open the http://0.0.0.0:8000 in your browser to see the widget UI
# close the browser window and Ctrl+C in terminal to exit
```

For more detail on usage of the various scripts see the main [README](README.md) file.

### 6) Make changes
Make whatever changes you want to the codebase. Create new branches for your changes and commit your changes with clear commit messages.

- Make sure to thoroughly test your changes locally before submitting a PR.

### 7) Submit PR
Once you are done making changes and want to submit a PR you can do in the "Source Control" tab in VS-code (or use git commands in terminal or the GitHub web interface if you prefer).

From the Source Control tab in your branch you click the "Create Pull Request" button to open the PR creation page.

---

Thank you for contributing!

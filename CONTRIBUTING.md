# Contributing Guidelines

Contributing involves forking the repo (or cloning it if you have write access, such as being part of the DCS group/org) and submitting a PR with your changes.

Internally DCS group works on issues, features, etc. according to the [DCS project](https://github.com/orgs/diverse-cognitive-systems-group/projects/1)

*No specific format is required for PRs at this point...as long as its reasonable/understandble and focuses on the core development areas needed (discussed below) it will be considered.*

## Step by Step Contributing Guide

First, install VSCode add the [DevContainers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.

### 1) Fork the repo (or clone if you have write access)
DCS group members should clone the repo directly.

You should now see the code on your local machine in VS-code's explorer window.

If you are not sure you can open the Command Palette (Cmd+Shift+P) and type/select "Terminal: Create New Terminal" to open a terminal window. In the terminla window type:

```sh
pwd && test -d dcs_simulation_engine && echo "✔ Folder structure looks correct" || echo "✖ Folder structure is incorrect"
```
*Note: this command will only work on Mac/Linux*

### 2) Add .env file
Create a .env file in the root of the project. (Just copy the .env.example file and rename it to .env then add your access keys for MongoDB, OpenRouter, etc.)

```sh
# Command to copy example env file to .env if you'd rather do it from terminal instead of manually in explorer.
cp .env.example .env
```

*Make sure you add your access keys (DCS group members can DM group admin for these)*

### 3) Launch dev container
From VS-code use Cmd+Shift+P to open the command palette, then type "Reopen in Container" and select that option to open the code in dev container. This will run the .devcontainer dev.Dockerfile to build the container and install all dependencies so we are all working in the same environment. The .devcontainer/devcontainer.json file specifies the vs-code settings for the container like which extensions to install, etc.

![launch dev container](images/launch_dev_container.png)

At this point you are all set up to start running scripts and/or changing code. To double check everything is working you can try running some unit tests or scripts as described below.

```sh
# run unit tests
# TODO: update this to run all unit/etc. tests to easily validate env setup for contributors
poetry run pytest tests/utils/test_file.py 

# run the Explore game using the CLI interface locally
poetry run python scripts/run_cli.py --game Explore
# type /quit or /exit to exit the game; /help for help

# run the Explore game using the WIDGET interface locally
poetry run python scripts/run_widget.py --game Explore
# open the http://0.0.0.0:8000 in your browser to see the widget UI
# close the browser window and Ctrl+C in terminal to exit
```

For more detail on usage of the various scripts see the main [README](README.md) file.

### 4) Make changes
Make whatever changes you want to the codebase. Create new branches for your changes and commit your changes with clear commit messages.

- Make sure to thoroughly test your changes locally before submitting a PR.

### 5) Submit PR
Once you are done making changes and want to submit a PR you can do in the "Source Control" tab in VS-code (or use git commands in terminal or the GitHub web interface if you prefer).

From the Source Control tab in your branch you click the "Create Pull Request" button to open the PR creation page.

TODO: add more details on PR process to make it easier on first time contributors.

⸻

Thank you for contributing!
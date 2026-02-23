# Character Coverage Analysis

An analysis of coverage of characters in DCS-SE, to identify gaps and guide future character development efforts.

Answers questions
- ...

## Workflow

```sh
# create a venv for this analysis (inside this analysis folder)
uv venv .venv-character-coverage
source .venv-character-coverage/bin/activate  # Windows: .venv-character-coverage\Scripts\activate

# install the engine (editable, so it tracks your current repo checkout)
uv pip install -e ../../..

# (optional but recommended for notebooks)
uv pip install ipykernel
python -m ipykernel install --user --name charcov --display-name "bio: charcov"
```

Open Jupyter and pick the "bio: charcov" kernel to run the notebooks in this analysis with the correct environment.

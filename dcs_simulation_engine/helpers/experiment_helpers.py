"""Helpers for experiment config discovery."""

from pathlib import Path


def get_experiment_config(experiment: str) -> str:
    """Return the path to an experiment YAML config by name or explicit file path."""
    possible_path = Path(experiment).expanduser()
    if possible_path.is_file() and possible_path.suffix.lower() in {".yaml", ".yml"}:
        return str(possible_path)

    experiments_dir = Path(__file__).resolve().parents[2] / "experiments"
    if not experiments_dir.exists():
        raise FileNotFoundError(f"Experiments directory not found: {experiments_dir}")

    for path in experiments_dir.glob("*.y*ml"):
        if path.stem.lower() == experiment.strip().lower():
            return str(path)

    deployments_dir = Path(__file__).resolve().parents[2] / "deployments"
    if deployments_dir.exists():
        for path in deployments_dir.glob("*/experiments/*.y*ml"):
            if path.stem.lower() == experiment.strip().lower():
                return str(path)

    raise FileNotFoundError(f"No experiment config matching {experiment!r} found in {experiments_dir}")

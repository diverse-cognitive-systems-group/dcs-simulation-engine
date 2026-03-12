"""Unit tests for the utility functions."""

from pathlib import Path

import pytest  # noqa: F401
from dcs_simulation_engine.utils.file import unique_fpath


def test_unique_fpath(tmp_path: Path) -> None:
    """Should return an incremented file path when the file exists."""
    p: Path = tmp_path / "file.txt"
    # when missing → same path
    assert unique_fpath(p) == p

    # create file.txt → next is file_1.txt
    p.write_text("x")
    assert unique_fpath(p) == tmp_path / "file_1.txt"

    # create file_1.txt → next is file_2.txt
    (tmp_path / "file_1.txt").write_text("y")
    assert unique_fpath(p) == tmp_path / "file_2.txt"

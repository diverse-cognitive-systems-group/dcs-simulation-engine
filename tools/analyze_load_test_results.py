#!/usr/bin/env python3
"""Generate Seaborn violin plots for load test JSON results.

Input schema is the JSON emitted by tests/manual/load_test.py.
"""

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import typer


def _load_results(path: Path) -> dict[str, Any]:
    """Load and validate top-level JSON structure."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected top-level JSON object.")
    clients = payload.get("clients")
    if not isinstance(clients, list):
        raise ValueError("Expected top-level 'clients' list.")
    return payload


def _load_metrics_csv(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load flattened metrics CSV emitted by tests/manual/load_test.py."""
    df = pd.read_csv(path)
    required = {"metric", "value_ms", "client_id", "game_number"}
    missing = required - set(df.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"CSV is missing required columns: {missing_str}")

    game_df = df[df["metric"] == "game_duration_ms"].copy()
    wait_df = df[df["metric"] == "wait_response_duration_ms"].copy()

    if not game_df.empty:
        game_df["game_duration_ms"] = game_df["value_ms"].astype(float)
        game_df["game_label"] = "g" + game_df["game_number"].astype(str)
        game_df["client_game"] = "c" + game_df["client_id"].astype(str) + "-g" + game_df["game_number"].astype(str)
    if not wait_df.empty:
        wait_df["wait_response_duration_ms"] = wait_df["value_ms"].astype(float)
        wait_df["game_label"] = "g" + wait_df["game_number"].astype(str)
        wait_df["client_game"] = "c" + wait_df["client_id"].astype(str) + "-g" + wait_df["game_number"].astype(str)

    return game_df, wait_df


def _flatten(payload: dict[str, Any], include_failed: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Flatten nested client/game payload into plotting rows.

    Returns:
        game_rows: one row per game with game_duration_ms
        wait_rows: one row per wait sample with wait_response_duration_ms
    """
    game_rows: list[dict[str, Any]] = []
    wait_rows: list[dict[str, Any]] = []

    for client in payload.get("clients", []):
        client_id = client.get("client_id")
        for game in client.get("game_results", []):
            success = bool(game.get("success"))
            if not include_failed and not success:
                continue

            game_number = game.get("game_number")
            game_duration_ms = game.get("game_duration_ms")
            if isinstance(game_duration_ms, (int, float)):
                game_rows.append(
                    {
                        "client_id": client_id,
                        "game_number": game_number,
                        "game_label": f"g{game_number}",
                        "client_game": f"c{client_id}-g{game_number}",
                        "game_duration_ms": float(game_duration_ms),
                    }
                )

            waits = game.get("wait_response_duration_ms", [])
            if not isinstance(waits, list):
                continue
            for idx, wait_ms in enumerate(waits, start=1):
                if not isinstance(wait_ms, (int, float)):
                    continue
                wait_rows.append(
                    {
                        "client_id": client_id,
                        "game_number": game_number,
                        "game_label": f"g{game_number}",
                        "client_game": f"c{client_id}-g{game_number}",
                        "sample_index": idx,
                        "wait_response_duration_ms": float(wait_ms),
                    }
                )

    return game_rows, wait_rows


def _plot_game_duration_by_client(game_df: pd.DataFrame, output: Path) -> None:
    """Violin plot: game_duration_ms grouped by client_id."""
    if game_df.empty:
        return
    plt.figure(figsize=(12, 6))
    sns.violinplot(
        data=game_df,
        x="client_id",
        y="game_duration_ms",
        inner="quartile",
        cut=0,
    )
    plt.title("Game Duration by Client")
    plt.xlabel("Client ID")
    plt.ylabel("game_duration_ms")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def _plot_wait_by_client(wait_df: pd.DataFrame, output: Path) -> None:
    """Violin plot: wait_response_duration_ms grouped by client_id."""
    if wait_df.empty:
        return
    plt.figure(figsize=(12, 6))
    sns.violinplot(
        data=wait_df,
        x="client_id",
        y="wait_response_duration_ms",
        inner="quartile",
        cut=0,
    )
    plt.title("Wait Response Duration by Client")
    plt.xlabel("Client ID")
    plt.ylabel("wait_response_duration_ms")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def _plot_wait_by_client_and_game(wait_df: pd.DataFrame, output: Path) -> None:
    """Violin plot: wait_response_duration_ms grouped by client_id and game_number."""
    if wait_df.empty:
        return
    plt.figure(figsize=(14, 7))
    sns.violinplot(
        data=wait_df,
        x="client_id",
        y="wait_response_duration_ms",
        hue="game_label",
        inner="quartile",
        cut=0,
        dodge=True,
    )
    plt.title("Wait Response Duration by Client and Game Number")
    plt.xlabel("Client ID")
    plt.ylabel("wait_response_duration_ms")
    plt.legend(title="Game #", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def _plot_mixed_game_duration_hist_density(game_df: pd.DataFrame, output: Path) -> None:
    """Histogram + KDE for game_duration_ms with all clients/games mixed."""
    if game_df.empty or "game_duration_ms" not in game_df.columns:
        return
    plt.figure(figsize=(12, 6))
    sns.histplot(
        data=game_df,
        x="game_duration_ms",
        bins=40,
        kde=True,
        stat="density",
        element="step",
        alpha=0.3,
    )
    _add_distribution_reference_lines(game_df["game_duration_ms"].to_numpy(dtype=float))
    plt.title("Game Duration Histogram + KDE (All Clients/Games Combined)")
    plt.xlabel("Duration (ms)")
    plt.ylabel("Density")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def _plot_mixed_wait_response_hist_density(wait_df: pd.DataFrame, output: Path) -> None:
    """Histogram + KDE for wait_response_duration_ms with all clients/games mixed."""
    if wait_df.empty or "wait_response_duration_ms" not in wait_df.columns:
        return
    plt.figure(figsize=(12, 6))
    sns.histplot(
        data=wait_df,
        x="wait_response_duration_ms",
        bins=40,
        kde=True,
        stat="density",
        element="step",
        alpha=0.3,
    )
    _add_distribution_reference_lines(wait_df["wait_response_duration_ms"].to_numpy(dtype=float))
    plt.title("Wait Response Histogram + KDE (All Clients/Games Combined)")
    plt.xlabel("Duration (ms)")
    plt.ylabel("Density")
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()


def _add_distribution_reference_lines(values: np.ndarray) -> None:
    """Overlay mean, median, and high-percentile vertical bars with legend values."""
    if values.size == 0:
        return

    mean = float(np.mean(values))
    median = float(np.median(values))
    p90 = float(np.percentile(values, 90))
    p95 = float(np.percentile(values, 95))
    p99 = float(np.percentile(values, 99))

    ax = plt.gca()
    ax.axvline(mean, color="crimson", linestyle="-", linewidth=2, label=f"mean={mean:.3f} ms")
    ax.axvline(median, color="darkorange", linestyle="--", linewidth=2, label=f"median={median:.3f} ms")
    ax.axvline(
        p90,
        color="royalblue",
        linestyle=":",
        linewidth=2,
        label=f"p90={p90:.3f} ms",
    )
    ax.axvline(
        p95,
        color="seagreen",
        linestyle="-.",
        linewidth=2,
        label=f"p95={p95:.3f} ms",
    )
    ax.axvline(
        p99,
        color="purple",
        linestyle=(0, (3, 1, 1, 1)),
        linewidth=2,
        label=f"p99={p99:.3f} ms",
    )
    ax.legend(loc="upper right", frameon=True)


def main(
    input: str = typer.Option(
        "load_test_results.json",
        help="Path to load test results JSON or *_metrics.csv.",
    ),
    output_dir: str = typer.Option("analysis/load_test", help="Directory to write plot files."),
    style: str = typer.Option("whitegrid", help="Seaborn style name (e.g. whitegrid, darkgrid, ticks)."),
    include_failed: bool = typer.Option(False, help="Include failed games if present."),
) -> None:
    """CLI entrypoint for generating violin plots from load test results."""
    input_path = Path(input)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(style=style)
    if input_path.suffix.lower() == ".csv":
        game_df, wait_df = _load_metrics_csv(input_path)
    else:
        payload = _load_results(input_path)
        game_rows, wait_rows = _flatten(payload, include_failed=include_failed)
        game_df = pd.DataFrame(game_rows)
        wait_df = pd.DataFrame(wait_rows)

    game_rows = len(game_df)
    wait_rows = len(wait_df)

    plot1 = output_dir / "violin_game_duration_by_client.png"
    plot2 = output_dir / "violin_wait_response_by_client.png"
    plot3 = output_dir / "violin_wait_response_by_client_and_game.png"
    plot4 = output_dir / "hist_kde_mixed_game_duration_ms.png"
    plot5 = output_dir / "hist_kde_mixed_wait_response_duration_ms.png"

    _plot_game_duration_by_client(game_df, plot1)
    _plot_wait_by_client(wait_df, plot2)
    _plot_wait_by_client_and_game(wait_df, plot3)
    _plot_mixed_game_duration_hist_density(game_df, plot4)
    _plot_mixed_wait_response_hist_density(wait_df, plot5)

    print(f"Input: {input_path}")
    print(f"Game rows: {game_rows}")
    print(f"Wait rows: {wait_rows}")
    print(f"Wrote: {plot1}")
    print(f"Wrote: {plot2}")
    print(f"Wrote: {plot3}")
    print(f"Wrote: {plot4}")
    print(f"Wrote: {plot5}")


if __name__ == "__main__":
    typer.run(main)

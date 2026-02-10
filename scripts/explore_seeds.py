#!/usr/bin/env python3
"""Explore deterministic table spawn seeds and recommend easy/medium/hard scenarios."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import yaml


@dataclass(frozen=True)
class SeedResult:
    seed: int
    n_objects: int
    difficulty: float
    clustering: float
    edge_ratio: float


def _load_base_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _simulate_positions(seed: int, n_objects: int, bounds: Tuple[float, float, float, float]) -> List[np.ndarray]:
    """Replicate `build_messy_table` placement logic without launching pybullet."""
    rng = np.random.RandomState(seed)
    x_min, x_max, y_min, y_max = bounds
    positions: List[np.ndarray] = []

    for _ in range(n_objects):
        chosen = None
        for _attempt in range(10):
            x = float(rng.uniform(x_min, x_max))
            y = float(rng.uniform(y_min, y_max))
            candidate = np.array([x, y], dtype=float)
            if all(np.linalg.norm(candidate - p) >= 0.08 for p in positions):
                chosen = candidate
                break
        if chosen is None:
            chosen = np.array(
                [float(rng.uniform(x_min, x_max)), float(rng.uniform(y_min, y_max))],
                dtype=float,
            )
        positions.append(chosen)
        # Consume random calls used for color assignment in real world builder.
        _ = rng.rand()
        _ = rng.rand()
        _ = rng.rand()

    return positions


def _difficulty_score(positions: List[np.ndarray], bounds: Tuple[float, float, float, float], n_objects: int) -> Tuple[float, float, float]:
    """Higher score means harder."""
    x_min, x_max, y_min, y_max = bounds

    # Clustering: inverse nearest-neighbor distance (normalized).
    nearest = []
    for i, pos in enumerate(positions):
        dists = [np.linalg.norm(pos - other) for j, other in enumerate(positions) if j != i]
        nearest.append(min(dists) if dists else 1.0)
    mean_nearest = float(np.mean(nearest))
    clustering = max(0.0, min(1.0, (0.25 - mean_nearest) / 0.25))

    # Edge proximity: fraction near table edge (within 4.5cm).
    edge_margin = 0.045
    edge_count = 0
    for pos in positions:
        x, y = pos
        if (
            (x - x_min) < edge_margin
            or (x_max - x) < edge_margin
            or (y - y_min) < edge_margin
            or (y_max - y) < edge_margin
        ):
            edge_count += 1
    edge_ratio = edge_count / max(1, n_objects)

    # Object-count factor expected by scenario family.
    count_factor = min(1.0, n_objects / 10.0)
    score = 0.45 * clustering + 0.35 * edge_ratio + 0.20 * count_factor
    return score, clustering, edge_ratio


def _pick_seed(candidates: List[SeedResult], target: float) -> SeedResult:
    return min(candidates, key=lambda r: abs(r.difficulty - target))


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore seeds for easy/medium/hard baseline scenarios")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--limit", type=int, default=1000, help="Search seeds in [0, limit)")
    args = parser.parse_args()

    cfg = _load_base_config(args.config)
    world_cfg = cfg["world"]["messy_table"]
    bounds = tuple(world_cfg["table_bounds_xy"])

    all_results: List[SeedResult] = []
    for n in (5, 7, 9):
        for seed in range(args.limit):
            positions = _simulate_positions(seed=seed, n_objects=n, bounds=bounds)  # type: ignore[arg-type]
            score, clustering, edge_ratio = _difficulty_score(positions, bounds, n)
            all_results.append(
                SeedResult(
                    seed=seed,
                    n_objects=n,
                    difficulty=score,
                    clustering=clustering,
                    edge_ratio=edge_ratio,
                )
            )

    easy = _pick_seed([r for r in all_results if r.n_objects == 5], target=0.22)
    medium = _pick_seed([r for r in all_results if r.n_objects == 7], target=0.48)
    hard = _pick_seed([r for r in all_results if r.n_objects == 9], target=0.72)

    print("Recommended seeds:")
    print(f"EASY   seed={easy.seed}   n={easy.n_objects}   score={easy.difficulty:.3f}   clustering={easy.clustering:.3f}   edge={easy.edge_ratio:.3f}")
    print(f"MEDIUM seed={medium.seed} n={medium.n_objects} score={medium.difficulty:.3f}   clustering={medium.clustering:.3f}   edge={medium.edge_ratio:.3f}")
    print(f"HARD   seed={hard.seed}   n={hard.n_objects}   score={hard.difficulty:.3f}   clustering={hard.clustering:.3f}   edge={hard.edge_ratio:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

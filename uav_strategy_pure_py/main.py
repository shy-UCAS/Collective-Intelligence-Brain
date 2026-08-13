"""Entry point for the pure Python agents02 replacement."""

from __future__ import annotations

import argparse
import json
import os
import random

import numpy as np

from uav_strategy_pure_py.memory_io import InMemoryUavIO
from uav_strategy_pure_py.mission_orchestrator import MissionOrchestrator


HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pure Python agents02 simulator")
    parser.add_argument(
        "--digraph-attrs",
        default=os.path.join(
            DATA_DIR, "manual_plan_graph", "manual_plan_graph_shaoxing_digraph_attrs.json"
        ),
    )
    parser.add_argument("--facilities", default=os.path.join(DATA_DIR, "facilities_shaoxing.json"))
    parser.add_argument(
        "--key-paths",
        default=None,
        help="Optional JSON file containing key_paths. Defaults to the shaoxing plan.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(HERE, "outputs"),
        help="Directory for the exported trajectory JSON.",
    )
    parser.add_argument("--max-rounds", type=int, default=200000)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    if args.key_paths:
        key_paths = load_json(args.key_paths)
    else:
        key_paths = [[0, 3], [1, 4], [2, 5]]

    digraph_attrs = load_json(args.digraph_attrs)

    io = InMemoryUavIO()
    orchestrator = MissionOrchestrator(
        digraph_attrs=digraph_attrs,
        key_paths=key_paths,
        facilities_file=args.facilities,
        io=io,
        output_dir=args.output_dir,
    )
    orchestrator.run(max_rounds=args.max_rounds)


if __name__ == "__main__":
    main()

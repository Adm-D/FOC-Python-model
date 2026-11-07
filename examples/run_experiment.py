"""Run a saved experiment without starting the web server."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pmsm_lab.config import SimulationConfig
from pmsm_lab.simulation import simulate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path, default=Path('outputs/experiment.npz'))
    args = parser.parse_args()
    config = SimulationConfig.model_validate_json(args.config.read_text()) if args.config else SimulationConfig()
    result = simulate(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, time=result.time, **result.signals,
                        config_json=config.model_dump_json(), metrics_json=json.dumps(result.metrics))
    print(json.dumps(result.metrics, indent=2))
    for warning in result.warnings:
        print(warning)
    print(f'Saved {args.output}')


if __name__ == '__main__':
    main()

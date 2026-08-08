"""Executa etapas reproduzíveis do pipeline dentro do contêiner."""

from __future__ import annotations

import argparse
import subprocess
import sys

COMMANDS = {
    "prepare": (
        ("-m", "src.data.translate", "--config", "configs/data.yaml"),
        ("-m", "src.data.prepare", "--config", "configs/data.yaml"),
    ),
    "train": (
        ("-m", "src.models.train_propensity", "--config", "configs/modeling.yaml"),
    ),
    "evaluate": (
        ("-m", "src.evaluation.replay", "--config", "configs/policy.yaml"),
    ),
}


def run(stage: str) -> None:
    """Executa uma etapa ou o pipeline completo, interrompendo na primeira falha."""
    selected_stages = tuple(COMMANDS) if stage == "all" else (stage,)
    for selected_stage in selected_stages:
        print(f"[pipeline] Iniciando etapa: {selected_stage}", flush=True)
        for arguments in COMMANDS[selected_stage]:
            subprocess.run((sys.executable, *arguments), check=True)
        print(f"[pipeline] Etapa concluída: {selected_stage}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa o pipeline M1–M4 containerizado.")
    parser.add_argument("stage", choices=("all", *COMMANDS), nargs="?", default="all")
    arguments = parser.parse_args()
    run(arguments.stage)


if __name__ == "__main__":
    main()

"""Testes do orquestrador dos jobs containerizados."""

import sys

from scripts import run_container_pipeline


def test_all_runs_every_stage_in_order(monkeypatch) -> None:
    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_run(command: tuple[str, ...], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr(run_container_pipeline.subprocess, "run", fake_run)

    run_container_pipeline.run("all")

    assert calls == [
        (
            (sys.executable, "-m", "src.data.translate", "--config", "configs/data.yaml"),
            True,
        ),
        (
            (sys.executable, "-m", "src.data.prepare", "--config", "configs/data.yaml"),
            True,
        ),
        (
            (
                sys.executable,
                "-m",
                "src.models.train_propensity",
                "--config",
                "configs/modeling.yaml",
            ),
            True,
        ),
        (
            (
                sys.executable,
                "-m",
                "src.evaluation.replay",
                "--config",
                "configs/policy.yaml",
            ),
            True,
        ),
    ]


def test_single_stage_runs_only_its_commands(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], *, check: bool) -> None:
        assert check is True
        calls.append(command)

    monkeypatch.setattr(run_container_pipeline.subprocess, "run", fake_run)

    run_container_pipeline.run("train")

    assert calls == [
        (
            sys.executable,
            "-m",
            "src.models.train_propensity",
            "--config",
            "configs/modeling.yaml",
        )
    ]

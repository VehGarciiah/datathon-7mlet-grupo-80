"""Executa replay factual comum para baseline e Thompson Sampling."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import yaml

from src.data.contracts import DataContractError
from src.data.translate import compute_sha256
from src.features.build_features import (
    ACTION_COLUMN,
    CONTEXT_COLUMNS,
    IDENTIFIER_COLUMN,
    TARGET_COLUMN,
)
from src.models.train_propensity import load_modeling_config, load_processed_splits
from src.policies.fixed import BestHistoricalActionPolicy
from src.policies.thompson_sampling import SegmentedThompsonSamplingPolicy


@dataclass(frozen=True)
class ReplayConfig:
    """Agrupa parâmetros congelados e caminhos do M4."""

    project_root: Path
    config_path: Path
    modeling_config_path: Path
    action_order: list[str]
    policy_id: str
    policy_version: str
    prior_alpha: float
    prior_beta: float
    segment_columns: list[str]
    minimum_support_per_action: int
    segment_selection_basis: str
    historical_reward_warm_start: bool
    state_artifact_path: Path
    evaluation_splits: list[str]
    stable_order_column: str
    seed_start: int
    seed_count: int
    bootstrap_iterations: int
    confidence_level: float
    bootstrap_random_seed: int
    require_positive_mean_lift: bool
    require_positive_lift_ci_lower: bool
    evaluation_path: Path
    seed_results_path: Path
    curves_path: Path
    comparison_plot_path: Path
    latest_mlflow_run_path: Path
    tracking_enabled: bool
    tracking_database_path: Path
    experiment_name: str
    run_name: str


def _read_yaml(path: Path) -> dict[str, Any]:
    """Carrega YAML obrigatório e rejeita conteúdo vazio."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise DataContractError(f"Configuração inválida ou vazia: {path}.")
    return content


def load_replay_config(config_path: str | Path = "configs/policy.yaml") -> ReplayConfig:
    """Resolve configuração do M4 e valida escolhas pré-registradas."""
    resolved_path = Path(config_path).resolve()
    project_root = resolved_path.parent.parent
    content = _read_yaml(resolved_path)
    policy = content["adaptive_policy"]
    segmentation = policy["segmentation"]
    initialization = policy["initialization"]
    replay = content["replay"]
    bootstrap = replay["bootstrap"]
    reports = content["reports"]
    tracking = content["tracking"]
    gate = replay["candidate_gate"]
    action_order = list(policy["action_order"])
    segment_columns = list(segmentation["columns"])
    evaluation_splits = list(replay["evaluation_splits"])

    if len(action_order) < 2 or len(set(action_order)) != len(action_order):
        raise DataContractError("O replay exige pelo menos duas ações únicas.")
    if not set(segment_columns).issubset(CONTEXT_COLUMNS):
        invalid = sorted(set(segment_columns) - set(CONTEXT_COLUMNS))
        raise DataContractError(f"Segmentos fora do contexto pré-decisão: {invalid}.")
    if set(evaluation_splits) != {"validation", "test"}:
        raise DataContractError("O M4 deve avaliar exatamente validação e teste.")
    if int(replay["seeds"]["count"]) < 30:
        raise DataContractError("O M4 exige no mínimo 30 seeds da política.")
    if replay["stable_order_column"] != IDENTIFIER_COLUMN:
        raise DataContractError("O replay deve usar event_id como ordem estável.")
    if not replay["update_only_on_accepted_events"]:
        raise DataContractError("Atualizar eventos rejeitados violaria o replay factual.")
    if not replay["reset_to_initial_state_per_split_and_seed"]:
        raise DataContractError("Cada split e seed deve começar do mesmo estado inicial.")

    return ReplayConfig(
        project_root=project_root,
        config_path=resolved_path,
        modeling_config_path=project_root / content["modeling_config_path"],
        action_order=action_order,
        policy_id=policy["id"],
        policy_version=policy["version"],
        prior_alpha=float(policy["prior"]["alpha"]),
        prior_beta=float(policy["prior"]["beta"]),
        segment_columns=segment_columns,
        minimum_support_per_action=int(segmentation["minimum_support_per_action"]),
        segment_selection_basis=str(segmentation["selection_basis"]),
        historical_reward_warm_start=bool(initialization["historical_reward_warm_start"]),
        state_artifact_path=project_root / policy["state_artifact_path"],
        evaluation_splits=evaluation_splits,
        stable_order_column=replay["stable_order_column"],
        seed_start=int(replay["seeds"]["start"]),
        seed_count=int(replay["seeds"]["count"]),
        bootstrap_iterations=int(bootstrap["iterations"]),
        confidence_level=float(bootstrap["confidence_level"]),
        bootstrap_random_seed=int(bootstrap["random_seed"]),
        require_positive_mean_lift=bool(gate["require_positive_mean_lift"]),
        require_positive_lift_ci_lower=bool(gate["require_positive_lift_ci_lower"]),
        evaluation_path=project_root / reports["evaluation_path"],
        seed_results_path=project_root / reports["seed_results_path"],
        curves_path=project_root / reports["curves_path"],
        comparison_plot_path=project_root / reports["comparison_plot_path"],
        latest_mlflow_run_path=project_root / reports["latest_mlflow_run_path"],
        tracking_enabled=bool(tracking["enabled"]),
        tracking_database_path=project_root / tracking["database_path"],
        experiment_name=tracking["experiment_name"],
        run_name=tracking["run_name"],
    )


def bootstrap_mean_interval(
    values: list[float] | np.ndarray,
    *,
    iterations: int,
    confidence_level: float,
    random_seed: int,
) -> dict[str, float]:
    """Estima intervalo percentil da média sem materializar matriz excessiva."""
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"lower": 0.0, "upper": 0.0}
    if iterations <= 0:
        raise DataContractError("O número de iterações bootstrap deve ser positivo.")
    if not 0 < confidence_level < 1:
        raise DataContractError("O nível de confiança deve estar entre 0 e 1.")

    rng = np.random.default_rng(random_seed)
    bootstrap_means = np.empty(iterations, dtype=float)
    batch_size = 250
    for start in range(0, iterations, batch_size):
        stop = min(start + batch_size, iterations)
        indices = rng.integers(0, array.size, size=(stop - start, array.size))
        bootstrap_means[start:stop] = array[indices].mean(axis=1)
    tail = (1 - confidence_level) / 2
    return {
        "lower": float(np.quantile(bootstrap_means, tail)),
        "upper": float(np.quantile(bootstrap_means, 1 - tail)),
    }


def run_single_replay(
    policy: Any,
    frame: pd.DataFrame,
    *,
    split_name: str,
    action_order: list[str],
    update_policy: bool,
    seed: int | None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Percorre eventos estáveis e revela recompensa apenas quando há coincidência."""
    ordered_frame = frame.sort_values(IDENTIFIER_COLUMN).reset_index(drop=True)
    action_counts = {action: 0 for action in action_order}
    accepted_rewards: list[int] = []
    rows: list[dict[str, Any]] = []
    cumulative_reward = 0
    accepted_events = 0
    exploration_events = 0
    fallback_events = 0

    for event_index, row in ordered_frame.iterrows():
        context = {column: row[column] for column in CONTEXT_COLUMNS}
        decision = policy.recommend(context, action_order)
        observed_action = str(row[ACTION_COLUMN])
        accepted = decision.action == observed_action
        observed_reward = int(row[TARGET_COLUMN]) if accepted else None
        action_counts[decision.action] += 1
        exploration_events += int(decision.is_exploration)
        fallback_events += int(decision.used_fallback)

        if accepted:
            accepted_events += 1
            cumulative_reward += int(observed_reward)
            accepted_rewards.append(int(observed_reward))
            if update_policy:
                feedback_id = f"replay:{split_name}:{seed}:{int(row[IDENTIFIER_COLUMN])}"
                applied = policy.update(
                    decision.action,
                    int(observed_reward),
                    context,
                    feedback_id=feedback_id,
                )
                if not applied:
                    raise RuntimeError("Feedback inédito foi identificado como duplicado.")

        rows.append(
            {
                "event_index": event_index + 1,
                "event_id": int(row[IDENTIFIER_COLUMN]),
                "recommended_action": decision.action,
                "observed_action": observed_action,
                "accepted": int(accepted),
                "observed_reward": observed_reward,
                "cumulative_reward": cumulative_reward,
                "cumulative_accepted_events": accepted_events,
                "cumulative_exploration_events": exploration_events,
            }
        )

    total_events = len(ordered_frame)
    summary = {
        "split": split_name,
        "seed": seed,
        "total_events": total_events,
        "accepted_events": accepted_events,
        "replay_coverage": accepted_events / total_events if total_events else 0.0,
        "conversions": cumulative_reward,
        "mean_reward": cumulative_reward / accepted_events if accepted_events else 0.0,
        "cumulative_reward": cumulative_reward,
        "exploration_events": exploration_events,
        "exploration_rate": exploration_events / total_events if total_events else 0.0,
        "fallback_events": fallback_events,
        "fallback_rate": fallback_events / total_events if total_events else 0.0,
        "action_distribution": {
            action: {
                "count": action_counts[action],
                "rate": action_counts[action] / total_events if total_events else 0.0,
            }
            for action in action_order
        },
        "accepted_rewards": accepted_rewards,
    }
    return summary, pd.DataFrame(rows)


def _aggregate_seed_results(
    seed_summaries: list[dict[str, Any]],
    baseline_summary: dict[str, Any],
    config: ReplayConfig,
    split_offset: int,
) -> dict[str, Any]:
    """Resume dispersão entre seeds e calcula lift contra a mesma baseline."""
    mean_rewards = np.array([item["mean_reward"] for item in seed_summaries])
    coverages = np.array([item["replay_coverage"] for item in seed_summaries])
    cumulative_rewards = np.array([item["cumulative_reward"] for item in seed_summaries])
    exploration_rates = np.array([item["exploration_rate"] for item in seed_summaries])
    baseline_reward = float(baseline_summary["mean_reward"])
    absolute_lifts = mean_rewards - baseline_reward
    relative_lifts = (
        absolute_lifts / baseline_reward if baseline_reward > 0 else np.zeros_like(absolute_lifts)
    )
    ci_seed = config.bootstrap_random_seed + split_offset

    absolute_interval = bootstrap_mean_interval(
        absolute_lifts,
        iterations=config.bootstrap_iterations,
        confidence_level=config.confidence_level,
        random_seed=ci_seed + 1,
    )
    mean_lift = float(absolute_lifts.mean())
    gate_checks = {
        "positive_mean_lift": mean_lift > 0,
        "positive_lift_ci_lower": absolute_interval["lower"] > 0,
    }
    required_checks = []
    if config.require_positive_mean_lift:
        required_checks.append(gate_checks["positive_mean_lift"])
    if config.require_positive_lift_ci_lower:
        required_checks.append(gate_checks["positive_lift_ci_lower"])

    return {
        "seed_count": len(seed_summaries),
        "mean_reward": {
            "mean": float(mean_rewards.mean()),
            "standard_deviation": float(mean_rewards.std(ddof=1)),
            "bootstrap_confidence_interval": bootstrap_mean_interval(
                mean_rewards,
                iterations=config.bootstrap_iterations,
                confidence_level=config.confidence_level,
                random_seed=ci_seed + 2,
            ),
        },
        "replay_coverage": {
            "mean": float(coverages.mean()),
            "standard_deviation": float(coverages.std(ddof=1)),
        },
        "cumulative_reward": {
            "mean": float(cumulative_rewards.mean()),
            "standard_deviation": float(cumulative_rewards.std(ddof=1)),
        },
        "exploration_rate": {
            "mean": float(exploration_rates.mean()),
            "standard_deviation": float(exploration_rates.std(ddof=1)),
        },
        "action_distribution_mean_rate": {
            action: float(
                np.mean([item["action_distribution"][action]["rate"] for item in seed_summaries])
            )
            for action in config.action_order
        },
        "lift_vs_fixed": {
            "absolute_mean": mean_lift,
            "absolute_standard_deviation": float(absolute_lifts.std(ddof=1)),
            "absolute_bootstrap_confidence_interval": absolute_interval,
            "relative_mean": float(relative_lifts.mean()),
            "relative_standard_deviation": float(relative_lifts.std(ddof=1)),
            "relative_bootstrap_confidence_interval": bootstrap_mean_interval(
                relative_lifts,
                iterations=config.bootstrap_iterations,
                confidence_level=config.confidence_level,
                random_seed=ci_seed + 3,
            ),
        },
        "candidate_gate": {
            "checks": gate_checks,
            "passed": all(required_checks),
        },
    }


def _build_curve_frame(
    split_name: str,
    baseline_trace: pd.DataFrame,
    adaptive_traces: list[pd.DataFrame],
    action_order: list[str],
) -> pd.DataFrame:
    """Agrega curvas evento a evento sem esconder dispersão entre seeds."""
    rewards = np.vstack(
        [trace["cumulative_reward"].to_numpy(dtype=float) for trace in adaptive_traces]
    )
    accepted = np.vstack(
        [trace["cumulative_accepted_events"].to_numpy(dtype=float) for trace in adaptive_traces]
    )
    explored = np.vstack(
        [trace["cumulative_exploration_events"].to_numpy(dtype=float) for trace in adaptive_traces]
    )
    event_index = baseline_trace["event_index"].to_numpy(dtype=int)
    result = pd.DataFrame(
        {
            "split": split_name,
            "event_index": event_index,
            "baseline_cumulative_reward": baseline_trace["cumulative_reward"],
            "baseline_cumulative_coverage": (
                baseline_trace["cumulative_accepted_events"] / event_index
            ),
            "adaptive_cumulative_reward_mean": rewards.mean(axis=0),
            "adaptive_cumulative_reward_lower": np.quantile(rewards, 0.025, axis=0),
            "adaptive_cumulative_reward_upper": np.quantile(rewards, 0.975, axis=0),
            "adaptive_cumulative_coverage_mean": (accepted / event_index).mean(axis=0),
            "adaptive_cumulative_exploration_rate_mean": (explored / event_index).mean(axis=0),
        }
    )
    for action in action_order:
        action_rates = np.vstack(
            [
                trace["recommended_action"].eq(action).cumsum().to_numpy(dtype=float) / event_index
                for trace in adaptive_traces
            ]
        )
        result[f"adaptive_{action}_selection_rate_mean"] = action_rates.mean(axis=0)
    return result


def _write_json(content: dict[str, Any], path: Path) -> None:
    """Persiste relatório JSON por substituição segura."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary_path.replace(path)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Grava tabela com diretório criado antecipadamente."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def _plot_comparison(curves: pd.DataFrame, path: Path) -> None:
    """Gera curvas de recompensa e exploração para os dois splits."""
    splits = [split for split in ["validation", "test"] if split in set(curves["split"])]
    figure, axes = plt.subplots(len(splits), 2, figsize=(14, 5 * len(splits)), squeeze=False)
    labels = {"validation": "Validação", "test": "Teste"}
    for row_index, split_name in enumerate(splits):
        frame = curves.loc[curves["split"].eq(split_name)]
        x_values = frame["event_index"].to_numpy(dtype=float)
        adaptive_mean = frame["adaptive_cumulative_reward_mean"].to_numpy(dtype=float)
        adaptive_lower = frame["adaptive_cumulative_reward_lower"].to_numpy(dtype=float)
        adaptive_upper = frame["adaptive_cumulative_reward_upper"].to_numpy(dtype=float)
        reward_axis = axes[row_index, 0]
        reward_axis.plot(x_values, frame["baseline_cumulative_reward"], label="Baseline fixa")
        reward_axis.plot(x_values, adaptive_mean, label="Thompson — média de seeds")
        reward_axis.fill_between(
            x_values,
            adaptive_lower,
            adaptive_upper,
            alpha=0.2,
            label="Faixa de 95% entre seeds",
        )
        reward_axis.set_title(f"Recompensa cumulativa — {labels[split_name]}")
        reward_axis.set_xlabel("Eventos processados")
        reward_axis.set_ylabel("Conversões factuais aceitas")
        reward_axis.legend()
        reward_axis.grid(alpha=0.25)

        exploration_axis = axes[row_index, 1]
        exploration_axis.plot(
            x_values,
            frame["adaptive_cumulative_exploration_rate_mean"],
            label="Taxa de exploração",
        )
        exploration_axis.plot(
            x_values,
            frame["adaptive_celular_selection_rate_mean"],
            label="Seleção de celular",
        )
        exploration_axis.set_title(f"Exploração e escolhas — {labels[split_name]}")
        exploration_axis.set_xlabel("Eventos processados")
        exploration_axis.set_ylabel("Proporção acumulada")
        exploration_axis.set_ylim(0, 1)
        exploration_axis.legend()
        exploration_axis.grid(alpha=0.25)

    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def _git_commit(project_root: Path) -> str:
    """Obtém o commit atual sem impedir execução fora de um checkout Git."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _log_mlflow_run(
    config: ReplayConfig,
    report: dict[str, Any],
    artifact_paths: list[Path],
) -> dict[str, str]:
    """Registra configuração, incerteza, gate e evidências do M4."""
    database_uri = f"sqlite:///{config.tracking_database_path.resolve().as_posix()}"
    mlflow.set_tracking_uri(database_uri)
    mlflow.set_experiment(config.experiment_name)
    test_fixed = report["splits"]["test"]["fixed_baseline"]
    test_adaptive = report["splits"]["test"]["adaptive_policy"]
    with mlflow.start_run(run_name=config.run_name) as run:
        gate_passed = report["selection"]["candidate_gate_passed"]
        mlflow.set_tags(
            {
                "milestone": "M4",
                "policy_id": config.policy_id,
                "candidate": str(gate_passed).lower(),
                "approved": "false",
                "rejected": str(not gate_passed).lower(),
                "causal_claim": "false",
            }
        )
        mlflow.log_params(
            {
                "prior_alpha": config.prior_alpha,
                "prior_beta": config.prior_beta,
                "segment_columns": ",".join(config.segment_columns),
                "minimum_support_per_action": config.minimum_support_per_action,
                "segment_selection_basis": config.segment_selection_basis,
                "historical_reward_warm_start": config.historical_reward_warm_start,
                "seed_start": config.seed_start,
                "seed_count": config.seed_count,
                "bootstrap_iterations": config.bootstrap_iterations,
                "confidence_level": config.confidence_level,
                "fit_split": "train_support_only",
                "evaluation_protocol": "logged_action_replay",
                "git_commit": report["reproducibility"]["git_commit"],
            }
        )
        mlflow.log_metrics(
            {
                "test_fixed_mean_reward": test_fixed["mean_reward"],
                "test_fixed_coverage": test_fixed["replay_coverage"],
                "test_adaptive_mean_reward": test_adaptive["mean_reward"]["mean"],
                "test_adaptive_coverage": test_adaptive["replay_coverage"]["mean"],
                "test_adaptive_exploration_rate": test_adaptive["exploration_rate"]["mean"],
                "test_absolute_lift": test_adaptive["lift_vs_fixed"]["absolute_mean"],
                "test_relative_lift": test_adaptive["lift_vs_fixed"]["relative_mean"],
                "test_lift_ci_lower": test_adaptive["lift_vs_fixed"][
                    "absolute_bootstrap_confidence_interval"
                ]["lower"],
                "test_lift_ci_upper": test_adaptive["lift_vs_fixed"][
                    "absolute_bootstrap_confidence_interval"
                ]["upper"],
            }
        )
        for path in artifact_paths:
            mlflow.log_artifact(str(path))
        return {
            "run_id": run.info.run_id,
            "experiment_id": run.info.experiment_id,
            "tracking_uri": mlflow.get_tracking_uri(),
            "run_name": config.run_name,
        }


def run_m4_evaluation(
    config_path: str | Path = "configs/policy.yaml",
    *,
    enable_tracking: bool | None = None,
) -> dict[str, Any]:
    """Executa política, replay, incerteza, gráficos e rastreamento do M4."""
    config = load_replay_config(config_path)
    modeling_config = load_modeling_config(config.modeling_config_path)
    if modeling_config.action_order != config.action_order:
        raise DataContractError("A ordem de ações diverge entre M3 e M4.")
    splits, preparation_metadata = load_processed_splits(modeling_config)
    train_frame = splits["train"]

    fixed_policy = BestHistoricalActionPolicy(
        config.action_order,
        policy_id=modeling_config.policy_id,
        version=modeling_config.policy_version,
        confidence_level=modeling_config.fixed_confidence_level,
    ).fit(train_frame)
    initial_policy = SegmentedThompsonSamplingPolicy(
        config.action_order,
        segment_columns=config.segment_columns,
        minimum_support_per_action=config.minimum_support_per_action,
        prior_alpha=config.prior_alpha,
        prior_beta=config.prior_beta,
        random_seed=config.seed_start,
        policy_id=config.policy_id,
        version=config.policy_version,
        historical_reward_warm_start=config.historical_reward_warm_start,
    ).fit_support(train_frame)
    initial_policy.save_state(config.state_artifact_path)

    split_reports: dict[str, Any] = {}
    seed_rows: list[dict[str, Any]] = []
    all_curves: list[pd.DataFrame] = []
    seeds = list(range(config.seed_start, config.seed_start + config.seed_count))

    for split_offset, split_name in enumerate(config.evaluation_splits):
        frame = splits[split_name]
        baseline_summary, baseline_trace = run_single_replay(
            fixed_policy,
            frame,
            split_name=split_name,
            action_order=config.action_order,
            update_policy=False,
            seed=None,
        )
        baseline_rewards = baseline_summary.pop("accepted_rewards")
        baseline_summary["bootstrap_confidence_interval"] = bootstrap_mean_interval(
            baseline_rewards,
            iterations=config.bootstrap_iterations,
            confidence_level=config.confidence_level,
            random_seed=config.bootstrap_random_seed + split_offset * 100,
        )

        adaptive_summaries: list[dict[str, Any]] = []
        adaptive_traces: list[pd.DataFrame] = []
        for seed in seeds:
            policy = initial_policy.clone_with_seed(seed)
            summary, trace = run_single_replay(
                policy,
                frame,
                split_name=split_name,
                action_order=config.action_order,
                update_policy=True,
                seed=seed,
            )
            summary.pop("accepted_rewards")
            adaptive_summaries.append(summary)
            adaptive_traces.append(trace)
            seed_rows.append(
                {
                    "split": split_name,
                    "seed": seed,
                    "mean_reward": summary["mean_reward"],
                    "cumulative_reward": summary["cumulative_reward"],
                    "accepted_events": summary["accepted_events"],
                    "replay_coverage": summary["replay_coverage"],
                    "exploration_rate": summary["exploration_rate"],
                    "fallback_rate": summary["fallback_rate"],
                    "celular_selection_rate": summary["action_distribution"]["celular"]["rate"],
                    "telefone_selection_rate": summary["action_distribution"]["telefone"]["rate"],
                    "absolute_lift_vs_fixed": summary["mean_reward"]
                    - baseline_summary["mean_reward"],
                    "relative_lift_vs_fixed": (
                        (summary["mean_reward"] - baseline_summary["mean_reward"])
                        / baseline_summary["mean_reward"]
                        if baseline_summary["mean_reward"] > 0
                        else 0.0
                    ),
                }
            )

        adaptive_report = _aggregate_seed_results(
            adaptive_summaries,
            baseline_summary,
            config,
            split_offset * 100,
        )
        split_reports[split_name] = {
            "fixed_baseline": baseline_summary,
            "adaptive_policy": adaptive_report,
        }
        all_curves.append(
            _build_curve_frame(
                split_name,
                baseline_trace,
                adaptive_traces,
                config.action_order,
            )
        )

    seed_results = pd.DataFrame(seed_rows)
    curves = pd.concat(all_curves, ignore_index=True)
    _write_csv(seed_results, config.seed_results_path)
    _write_csv(curves, config.curves_path)
    _plot_comparison(curves, config.comparison_plot_path)

    gates_by_split = {
        split_name: split_reports[split_name]["adaptive_policy"]["candidate_gate"]["passed"]
        for split_name in config.evaluation_splits
    }
    overall_gate = all(gates_by_split.values())
    report = {
        "schema_version": "1.0.0",
        "milestone": "M4",
        "policy": {
            "policy_id": config.policy_id,
            "policy_version": config.policy_version,
            "family": "thompson_sampling",
            "reward_distribution": "beta_bernoulli",
            "prior": {"alpha": config.prior_alpha, "beta": config.prior_beta},
            "segment_columns": config.segment_columns,
            "minimum_support_per_action": config.minimum_support_per_action,
            "segment_selection_basis": config.segment_selection_basis,
            "supported_segment_count": len(initial_policy.segment_posteriors),
            "observed_segment_count": len(initial_policy.segment_support),
            "sparse_segment_fallback": "global_action_posterior",
            "historical_reward_warm_start": config.historical_reward_warm_start,
            "update_rule": "Somente o braço recomendado em eventos aceitos no replay.",
            "duplicate_feedback_rule": "feedback_id aplicado no máximo uma vez.",
            "state_persistence": "JSON versionado com substituição atômica.",
        },
        "evaluation_protocol": {
            "name": "logged_action_replay",
            "stable_order_column": config.stable_order_column,
            "seed_count": config.seed_count,
            "seeds": seeds,
            "bootstrap_iterations": config.bootstrap_iterations,
            "confidence_level": config.confidence_level,
            "state_reset_per_split_and_seed": True,
            "counterfactual_rule": "Eventos sem coincidência de ação não revelam recompensa.",
            "regret": {
                "value": None,
                "reason": (
                    "Não existe referência contrafactual válida para calcular regret factual."
                ),
            },
        },
        "splits": split_reports,
        "selection": {
            "evaluation_splits": config.evaluation_splits,
            "gates_by_split": gates_by_split,
            "candidate_gate_passed": overall_gate,
            "status": "candidate" if overall_gate else "rejected",
            "rollback_policy": modeling_config.policy_id,
            "interpretation": (
                "A política adaptativa só é candidata quando o lift médio e o limite "
                "inferior do intervalo são positivos."
            ),
        },
        "reproducibility": {
            "git_commit": _git_commit(config.project_root),
            "policy_config_sha256": compute_sha256(config.config_path),
            "preparation_metadata_sha256": compute_sha256(
                config.project_root / "data/processed/preparation.metadata.json"
            ),
            "split_hashes": {
                name: preparation_metadata["outputs"][name]["sha256"]
                for name in ["train", "validation", "test"]
            },
        },
        "artifacts": {
            "initial_policy_state": str(
                config.state_artifact_path.relative_to(config.project_root)
            ).replace("\\", "/"),
            "initial_policy_state_sha256": compute_sha256(config.state_artifact_path),
            "seed_results": str(config.seed_results_path.relative_to(config.project_root)).replace(
                "\\", "/"
            ),
            "curves": str(config.curves_path.relative_to(config.project_root)).replace("\\", "/"),
            "comparison_plot": str(
                config.comparison_plot_path.relative_to(config.project_root)
            ).replace("\\", "/"),
        },
        "limitations": [
            "O replay é observacional e condicionado à coincidência com a ação histórica.",
            (
                "Coberturas diferentes tornam recompensa cumulativa uma medida de apoio, "
                "não um lift causal."
            ),
            (
                "A propensão da política histórica é desconhecida; IPS não foi usado como "
                "evidência principal."
            ),
            (
                "A ausência de contrafactual impede afirmar o resultado de uma troca de "
                "canal por cliente."
            ),
            "A política deve permanecer rejeitada se o intervalo de lift incluir zero.",
        ],
    }
    _write_json(report, config.evaluation_path)

    should_track = config.tracking_enabled if enable_tracking is None else enable_tracking
    if should_track:
        tracking_info = _log_mlflow_run(
            config,
            report,
            [
                config.config_path,
                config.evaluation_path,
                config.seed_results_path,
                config.curves_path,
                config.comparison_plot_path,
                config.state_artifact_path,
            ],
        )
        _write_json(tracking_info, config.latest_mlflow_run_path)
    return report


def main() -> None:
    """Executa o M4 pela linha de comando."""
    parser = argparse.ArgumentParser(
        description="Avalia Thompson Sampling e baseline fixa por replay factual."
    )
    parser.add_argument(
        "--config",
        default="configs/policy.yaml",
        help="Caminho da configuração de política.",
    )
    parser.add_argument(
        "--no-tracking",
        action="store_true",
        help="Desativa o registro MLflow nesta execução.",
    )
    arguments = parser.parse_args()
    report = run_m4_evaluation(arguments.config, enable_tracking=not arguments.no_tracking)
    test = report["splits"]["test"]
    adaptive = test["adaptive_policy"]
    print(
        "M4 concluído: "
        f"baseline={test['fixed_baseline']['mean_reward']:.4f}, "
        f"Thompson={adaptive['mean_reward']['mean']:.4f}, "
        f"lift={adaptive['lift_vs_fixed']['absolute_mean']:.4f}, "
        f"gate={adaptive['candidate_gate']['passed']}."
    )


if __name__ == "__main__":
    main()

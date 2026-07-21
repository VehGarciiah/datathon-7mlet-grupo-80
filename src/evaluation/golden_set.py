"""Executa os cinco casos sintéticos contra a mesma aplicação FastAPI."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.service import load_api_config
from src.data.contracts import DataContractError
from src.data.translate import compute_sha256


def _write_json(content: dict[str, Any], path: Path) -> None:
    """Persiste relatório por substituição no mesmo diretório."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def run_golden_set(
    config_path: str | Path = "configs/api.yaml",
    *,
    database_path: str | Path | None = None,
) -> dict[str, Any]:
    """Valida contrato, respostas esperadas e revisão humana dos cinco casos."""
    config = load_api_config(config_path)
    fixture = json.loads(config.golden_fixture_path.read_text(encoding="utf-8"))
    cases = fixture.get("cases", [])
    case_ids = [case.get("case_id") for case in cases]
    if len(cases) != 5 or len(set(case_ids)) != 5:
        raise DataContractError("O golden set deve conter exatamente cinco case_id únicos.")

    temporary_directory = None
    if database_path is None:
        temporary_directory = tempfile.TemporaryDirectory(prefix="datathon-golden-")
        selected_database = Path(temporary_directory.name) / "golden_set.db"
    else:
        selected_database = Path(database_path)

    try:
        app = create_app(config_path, database_path=selected_database)
        with TestClient(app) as client:
            readiness = client.get("/ready")
            if readiness.status_code != 200:
                raise RuntimeError(f"API não está pronta para golden set: {readiness.json()}.")

            results: list[dict[str, Any]] = []
            for case in cases:
                response = client.post("/v1/recommendations", json=case["request"])
                response_content = response.json()
                expected = case["expected"]
                contract_passed = response.status_code == 201 and all(
                    response_content.get(field) == expected_value
                    for field, expected_value in expected.items()
                )
                results.append(
                    {
                        "case_id": case["case_id"],
                        "scenario": case["scenario"],
                        "http_status": response.status_code,
                        "recommended_action": response_content.get("recommended_action"),
                        "policy_id": response_content.get("policy_id"),
                        "policy_version": response_content.get("policy_version"),
                        "model_version": response_content.get("model_version"),
                        "is_exploration": response_content.get("is_exploration"),
                        "used_fallback": response_content.get("used_fallback"),
                        "reason": response_content.get("reason"),
                        "expected": expected,
                        "contract_passed": contract_passed,
                        "human_review": case["human_review"],
                        "audit_context_used_by_policy": False,
                    }
                )

        report = {
            "schema_version": "1.0.0",
            "milestone": "M5",
            "fixture_sha256": compute_sha256(config.golden_fixture_path),
            "api_config_sha256": compute_sha256(config.config_path),
            "case_count": len(results),
            "passed_count": sum(item["contract_passed"] for item in results),
            "all_cases_passed": all(item["contract_passed"] for item in results),
            "readiness": readiness.json(),
            "cases": results,
            "interpretation": (
                "Casos sintéticos revisam estabilidade e contrato; não demonstram efeito causal."
            ),
        }
        _write_json(report, config.golden_results_path)
        return report
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()


def main() -> None:
    """Executa golden set pela linha de comando."""
    parser = argparse.ArgumentParser(description="Executa os cinco casos do golden set na API.")
    parser.add_argument(
        "--config",
        default="configs/api.yaml",
        help="Caminho da configuração do serving.",
    )
    arguments = parser.parse_args()
    report = run_golden_set(arguments.config)
    print(f"Golden set concluído: {report['passed_count']}/{report['case_count']} casos aprovados.")


if __name__ == "__main__":
    main()

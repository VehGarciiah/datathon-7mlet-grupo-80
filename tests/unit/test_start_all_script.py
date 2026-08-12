"""Contratos do inicializador da stack no Windows com Podman/WSL."""

from pathlib import Path


def test_start_all_repairs_unavailable_podman_ports_with_local_ssh_forwards() -> None:
    source = Path("scripts/start-all.ps1").read_text(encoding="utf-8")

    assert "function Start-PodmanPortForward" in source
    assert "127.0.0.1:$port`:$containerIp`:$containerPort" in source
    assert "ExitOnForwardFailure=yes" in source
    assert "StartedAtFileTimeUtc" in source
    assert "Start-PodmanPortForward -Forwards $publishedForwards" in source
    assert "if (-not (Test-HttpEndpoint -Uri $webHealthUri))" in source


def test_start_all_forwards_every_published_development_port() -> None:
    source = Path("scripts/start-all.ps1").read_text(encoding="utf-8")

    expected_containers = {
        "datathon-observability-crm-web-1",
        "datathon-observability-crm-api-1",
        "datathon-observability-crm-postgres-1",
        "datathon-observability-api-1",
        "datathon-observability-flagd-1",
        "datathon-observability-mlflow-1",
        "datathon-observability-prometheus-1",
        "datathon-observability-alertmanager-1",
        "datathon-observability-grafana-1",
        "datathon-observability-airflow-1",
    }

    for container in expected_containers:
        assert container in source
    assert "$publishedForwards += [pscustomobject]" in source

[CmdletBinding()]
param(
    [ValidateRange(60, 1800)]
    [int]$TimeoutSeconds = 600,

    [switch]$SkipBuild,

    [switch]$WithoutAirflow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Podman {
    param(
        [Parameter(Mandatory)]
        [string[]]$CommandArguments
    )

    & podman @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao executar: podman $($CommandArguments -join ' ')"
    }
}

function Get-ConfiguredPort {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [int]$DefaultValue
    )

    $environmentValue = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($environmentValue)) {
        return [int]$environmentValue
    }

    $envFile = Join-Path $projectRoot '.env'
    if (Test-Path -LiteralPath $envFile) {
        $match = Get-Content -LiteralPath $envFile |
            Where-Object { $_ -match "^$([regex]::Escape($Name))=(.+)$" } |
            Select-Object -Last 1
        if ($match -and $match -match '^[^=]+=(.+)$') {
            return [int]$Matches[1].Trim()
        }
    }

    return $DefaultValue
}

function Wait-Container {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [datetime]$Deadline
    )

    while ([datetime]::UtcNow -lt $Deadline) {
        $state = & podman inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $Name 2>$null
        if ($LASTEXITCODE -eq 0 -and $state) {
            $parts = $state.Trim().Split('|')
            $running = $parts[0] -eq 'running'
            $healthReady = $parts[1] -eq 'none' -or $parts[1] -eq 'healthy'
            if ($running -and $healthReady) {
                Write-Host "[online] $Name"
                return
            }
            if ($parts[0] -in @('exited', 'dead') -or $parts[1] -eq 'unhealthy') {
                & podman logs --tail 80 $Name
                throw "Container $Name terminou em estado $state."
            }
        }
        Start-Sleep -Seconds 3
    }

    & podman logs --tail 80 $Name
    throw "Timeout aguardando o container $Name."
}

function Wait-HttpEndpoint {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [uri]$Uri,

        [Parameter(Mandatory)]
        [datetime]$Deadline
    )

    while ([datetime]::UtcNow -lt $Deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "[http]   $Name -> $Uri"
                return
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }

    throw "Timeout aguardando $Name em $Uri."
}

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory)]
        [uri]$Uri,

        [ValidateRange(1, 30)]
        [int]$TimeoutSeconds = 3
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Stop-ProjectPortForwards {
    $stateFile = Join-Path $projectRoot 'runtime/podman-port-forward.json'
    if (-not (Test-Path -LiteralPath $stateFile)) {
        return
    }

    try {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        $processIds = @($state.ProcessId)
        $processStartTimes = @($state.StartedAtFileTimeUtc)
        for ($index = 0; $index -lt $processIds.Count; $index++) {
            $processId = $processIds[$index]
            $process = Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue
            $sameProcess = $index -lt $processStartTimes.Count -and
                $process -and
                $process.StartTime.ToFileTimeUtc() -eq [long]$processStartTimes[$index]
            if ($sameProcess -and $process.ProcessName -eq 'ssh') {
                Stop-Process -Id $process.Id -Force
            }
        }
    } catch {
        Write-Warning "Nao foi possivel encerrar todos os encaminhamentos anteriores: $($_.Exception.Message)"
    } finally {
        Remove-Item -LiteralPath $stateFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-PodmanPortForward {
    param(
        [Parameter(Mandatory)]
        [object[]]$Forwards
    )

    if ($env:OS -ne 'Windows_NT') {
        return
    }

    $sshCommand = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if (-not $sshCommand) {
        throw 'O encaminhamento de portas do WSL falhou e o cliente OpenSSH do Windows nao foi encontrado.'
    }

    $machineOutput = & podman machine inspect 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $machineOutput) {
        throw 'Nao foi possivel obter a configuracao da maquina Podman para reparar as portas.'
    }
    $machine = ($machineOutput -join "`n" | ConvertFrom-Json | Select-Object -First 1)

    $runtimeDirectory = Join-Path $projectRoot 'runtime'
    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    Stop-ProjectPortForwards

    $activeForwards = @()
    foreach ($forward in @($Forwards | Sort-Object -Property HostPort -Unique)) {
        $port = [int]$forward.HostPort
        $containerPort = [int]$forward.ContainerPort
        $containerIp = & podman inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $forward.ContainerName 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($containerIp)) {
            Write-Warning "Porta $port nao foi encaminhada: IP do container $($forward.ContainerName) indisponivel."
            continue
        }
        $containerIp = $containerIp.Trim()

        $errorLog = Join-Path $runtimeDirectory "podman-port-forward-$port.err.log"
        $outputLog = Join-Path $runtimeDirectory "podman-port-forward-$port.out.log"
        Remove-Item -LiteralPath $errorLog, $outputLog -Force -ErrorAction SilentlyContinue

        $arguments = @(
            '-N',
            '-T',
            '-o', 'BatchMode=yes',
            '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=3',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=NUL',
            '-i', ('"{0}"' -f $machine.SSHConfig.IdentityPath),
            '-p', [string]$machine.SSHConfig.Port,
            '-L', "127.0.0.1:$port`:$containerIp`:$containerPort",
            "$($machine.SSHConfig.RemoteUsername)@127.0.0.1"
        )

        $process = Start-Process `
            -FilePath $sshCommand.Source `
            -ArgumentList $arguments `
            -WindowStyle Hidden `
            -RedirectStandardOutput $outputLog `
            -RedirectStandardError $errorLog `
            -PassThru

        Start-Sleep -Milliseconds 750
        $process.Refresh()
        if ($process.HasExited) {
            $details = if (Test-Path -LiteralPath $errorLog) {
                (Get-Content -LiteralPath $errorLog -Raw).Trim()
            } else {
                'sem detalhes'
            }
            Write-Warning "Porta $port nao foi encaminhada: $details"
            continue
        }

        $activeForwards += [pscustomobject]@{
            ProcessId = $process.Id
            StartedAtFileTimeUtc = $process.StartTime.ToFileTimeUtc()
            Port = $port
            ContainerName = $forward.ContainerName
            ContainerIp = $containerIp
            ContainerPort = $containerPort
        }
    }

    if ($activeForwards.Count -eq 0) {
        throw 'Nao foi possivel criar nenhum encaminhamento de porta entre Windows e Podman.'
    }

    $stateFile = Join-Path $runtimeDirectory 'podman-port-forward.json'
    $activeForwards | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
    Write-Host "[rede]   Encaminhamento Podman/WSL recuperado para $($activeForwards.Count) porta(s)."
}

Push-Location $projectRoot
try {
    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        throw 'Podman nao foi encontrado no PATH.'
    }

    & podman info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Iniciando a maquina do Podman...'
        & podman machine start
        if ($LASTEXITCODE -ne 0) {
            throw 'Nao foi possivel iniciar a maquina do Podman.'
        }
    }

    if (-not $SkipBuild) {
        Write-Host 'Compilando todas as imagens, inclusive jobs e Airflow...'
        Invoke-Podman -CommandArguments @(
            'compose',
            '--profile', 'jobs',
            '--profile', 'orchestration',
            'build'
        )
    }

    $upArguments = @('compose')
    if (-not $WithoutAirflow) {
        $upArguments += @('--profile', 'orchestration')
    }
    $upArguments += @('up', '-d')

    Write-Host 'Subindo os servicos persistentes...'
    Invoke-Podman -CommandArguments $upArguments

    $services = @(
        'api',
        'flagd',
        'crm-postgres',
        'crm-api',
        'crm-web',
        'process-exporter',
        'mlflow',
        'prometheus',
        'alertmanager',
        'loki',
        'alloy',
        'tempo',
        'otel-collector',
        'grafana'
    )
    if (-not $WithoutAirflow) {
        $services += 'airflow'
    }

    $deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
    foreach ($service in $services) {
        Wait-Container -Name "datathon-observability-$service-1" -Deadline $deadline
    }

    $webPort = Get-ConfiguredPort -Name 'CRM_WEB_PORT' -DefaultValue 80
    $crmApiPort = Get-ConfiguredPort -Name 'CRM_API_PORT' -DefaultValue 8081
    $crmDatabasePort = Get-ConfiguredPort -Name 'CRM_DATABASE_PORT' -DefaultValue 5433
    $apiPort = Get-ConfiguredPort -Name 'API_PORT' -DefaultValue 8000
    $flagdPort = Get-ConfiguredPort -Name 'FLAGD_PORT' -DefaultValue 8013
    $flagdManagementPort = Get-ConfiguredPort -Name 'FLAGD_MANAGEMENT_PORT' -DefaultValue 8014
    $mlflowPort = Get-ConfiguredPort -Name 'MLFLOW_PORT' -DefaultValue 5000
    $prometheusPort = Get-ConfiguredPort -Name 'PROMETHEUS_PORT' -DefaultValue 9090
    $alertmanagerPort = Get-ConfiguredPort -Name 'ALERTMANAGER_PORT' -DefaultValue 9093
    $grafanaPort = Get-ConfiguredPort -Name 'GRAFANA_PORT' -DefaultValue 3000

    $publishedForwards = @(
        [pscustomobject]@{ HostPort = $webPort; ContainerName = 'datathon-observability-crm-web-1'; ContainerPort = 80 },
        [pscustomobject]@{ HostPort = $crmApiPort; ContainerName = 'datathon-observability-crm-api-1'; ContainerPort = 8081 },
        [pscustomobject]@{ HostPort = $crmDatabasePort; ContainerName = 'datathon-observability-crm-postgres-1'; ContainerPort = 5432 },
        [pscustomobject]@{ HostPort = $apiPort; ContainerName = 'datathon-observability-api-1'; ContainerPort = 8000 },
        [pscustomobject]@{ HostPort = $flagdPort; ContainerName = 'datathon-observability-flagd-1'; ContainerPort = 8013 },
        [pscustomobject]@{ HostPort = $flagdManagementPort; ContainerName = 'datathon-observability-flagd-1'; ContainerPort = 8014 },
        [pscustomobject]@{ HostPort = $mlflowPort; ContainerName = 'datathon-observability-mlflow-1'; ContainerPort = 5000 },
        [pscustomobject]@{ HostPort = $prometheusPort; ContainerName = 'datathon-observability-prometheus-1'; ContainerPort = 9090 },
        [pscustomobject]@{ HostPort = $alertmanagerPort; ContainerName = 'datathon-observability-alertmanager-1'; ContainerPort = 9093 },
        [pscustomobject]@{ HostPort = $grafanaPort; ContainerName = 'datathon-observability-grafana-1'; ContainerPort = 3000 }
    )
    if (-not $WithoutAirflow) {
        $airflowPort = Get-ConfiguredPort -Name 'AIRFLOW_PORT' -DefaultValue 8080
        $publishedForwards += [pscustomobject]@{
            HostPort = $airflowPort
            ContainerName = 'datathon-observability-airflow-1'
            ContainerPort = 8080
        }
    }

    $webHealthUri = [uri]"http://127.0.0.1:$webPort/health"
    $portForwardState = Join-Path $projectRoot 'runtime/podman-port-forward.json'
    if (Test-Path -LiteralPath $portForwardState) {
        Stop-ProjectPortForwards
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-HttpEndpoint -Uri $webHealthUri)) {
        Write-Warning 'Containers saudaveis, mas as portas do Podman nao estao acessiveis no Windows. Reparando o encaminhamento WSL...'
        Start-PodmanPortForward -Forwards $publishedForwards
    }

    $httpDeadline = [datetime]::UtcNow.AddSeconds(90)
    Wait-HttpEndpoint -Name 'CRM Web' -Uri $webHealthUri -Deadline $httpDeadline
    Wait-HttpEndpoint -Name 'CRM API' -Uri "http://127.0.0.1:$crmApiPort/actuator/health/readiness" -Deadline $httpDeadline
    Wait-HttpEndpoint -Name 'API de recomendacoes' -Uri "http://127.0.0.1:$apiPort/ready" -Deadline $httpDeadline
    Wait-HttpEndpoint -Name 'OpenFeature flagd' -Uri "http://127.0.0.1:$flagdManagementPort/readyz" -Deadline $httpDeadline
    Wait-HttpEndpoint -Name 'MLflow' -Uri "http://127.0.0.1:$mlflowPort/" -Deadline $httpDeadline
    Wait-HttpEndpoint -Name 'Prometheus' -Uri "http://127.0.0.1:$prometheusPort/-/ready" -Deadline $httpDeadline
    Wait-HttpEndpoint -Name 'Grafana' -Uri "http://127.0.0.1:$grafanaPort/api/health" -Deadline $httpDeadline

    if (-not $WithoutAirflow) {
        Wait-HttpEndpoint -Name 'Airflow' -Uri "http://127.0.0.1:$airflowPort/api/v2/monitor/health" -Deadline $httpDeadline
    }

    Write-Host ''
    Write-Host 'Stack compilado e online:'
    Write-Host "- CRM Web:    http://127.0.0.1:$webPort/"
    Write-Host "- CRM Swagger: http://127.0.0.1:$crmApiPort/"
    Write-Host "- ML API:     http://127.0.0.1:$apiPort/docs"
    Write-Host "- flagd:      http://127.0.0.1:$flagdManagementPort/readyz"
    Write-Host "- MLflow:     http://127.0.0.1:$mlflowPort/"
    Write-Host "- Prometheus: http://127.0.0.1:$prometheusPort/"
    Write-Host "- Grafana:    http://127.0.0.1:$grafanaPort/"
    if (-not $WithoutAirflow) {
        Write-Host "- Airflow:    http://127.0.0.1:$airflowPort/"
    }
} finally {
    Pop-Location
}

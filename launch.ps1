#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ImageName = 'flightmare'
$DockerfileDir = $PSScriptRoot

function Invoke-Docker {
    param(
        [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
        [string[]] $Args
    )

    & docker @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($Args -join ' ') fallo con codigo $LASTEXITCODE"
    }
}

function Stop-FlightmareContainers {
    Write-Host "==> Deteniendo contenedores de $ImageName..."
    $containerIds = docker ps -q --filter "ancestor=$ImageName" 2>$null
    if ($containerIds) {
        foreach ($id in $containerIds) {
            docker stop $id 2>$null | Out-Null
        }
    }
}

function Remove-FlightmareImage {
    Write-Host "==> Eliminando imagen $ImageName..."
    docker rmi -f $ImageName 2>$null | Out-Null
}

function Invoke-Rebuild {
    Stop-FlightmareContainers
    Remove-FlightmareImage
    Write-Host '==> Build desde cero (sin cache)...'
    Invoke-Docker build --no-cache -t $ImageName $DockerfileDir
}

function Invoke-BuildOnly {
    Write-Host '==> Build con cache...'
    Invoke-Docker build -t $ImageName $DockerfileDir
}

function Invoke-SmokeTest {
    Write-Host '==> Smoke test...'
    Invoke-Docker run --rm $ImageName python3 -c `
        "import flightgym; from rpg_baselines.common.policies import MlpPolicy; print('flightgym + rpg_baselines OK')"
    Invoke-Docker run --rm $ImageName python3 -c `
        "import ruamel.yaml; print('ruamel.yaml', ruamel.yaml.version_info)"
}

function Show-SuccessMessage {
    Write-Host ''
    Write-Host 'Listo. Entra al contenedor con:'
    Write-Host '  .\launch.ps1 run'
    Write-Host "  o: docker run -it --rm -v `"${DockerfileDir}:/home/flightmare`" -w /home/flightmare $ImageName bash"
    Write-Host ''
    Write-Host 'Prueba RL (headless, sin graficos):'
    Write-Host '  cd /home/flightmare/flightrl/examples'
    Write-Host '  export MPLBACKEND=Agg'
    Write-Host '  python3 run_drone_control.py --train 0 --render 0'
}

function Show-Help {
    Write-Host 'Uso: .\launch.ps1 [comando]'
    Write-Host ''
    Write-Host '  .\launch.ps1         Rebuild completo sin cache + smoke test'
    Write-Host '  .\launch.ps1 build   Build con cache + smoke test'
    Write-Host '  .\launch.ps1 run     Abrir shell interactivo en el contenedor'
    Write-Host '  .\launch.ps1 help    Mostrar esta ayuda'
}

function Invoke-Run {
    docker image inspect $ImageName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "La imagen $ImageName no existe. Ejecuta: .\launch.ps1"
        exit 1
    }
    Invoke-Docker run -it --rm `
        -v "${DockerfileDir}:/home/flightmare" `
        -w /home/flightmare `
        $ImageName bash
}

$command = if ($args.Count -gt 0) { $args[0] } else { '' }

try {
    switch -Regex ($command) {
        '^run$' {
            Invoke-Run
        }
        '^build$' {
            Invoke-BuildOnly
            Invoke-SmokeTest
            Show-SuccessMessage
        }
        '^(help|-h|--help)$' {
            Show-Help
        }
        '^$' {
            Invoke-Rebuild
            Invoke-SmokeTest
            Show-SuccessMessage
        }
        default {
            Write-Host "Opcion desconocida: $command"
            Show-Help
            exit 1
        }
    }
}
catch {
    Write-Host ''
    Write-Host 'ERROR: fallo el build o el smoke test.'
    if ($_.Exception.Message -notmatch '^docker ') {
        Write-Host $_.Exception.Message
    }
    exit 1
}

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"
$desktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"

if (-not (Test-Path -LiteralPath $envFile)) {
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $jwtBytes = New-Object byte[] 32
        $databaseBytes = New-Object byte[] 24
        $random.GetBytes($jwtBytes)
        $random.GetBytes($databaseBytes)
        $jwtSecret = [BitConverter]::ToString($jwtBytes).Replace("-", "")
        $databasePassword = [BitConverter]::ToString($databaseBytes).Replace("-", "")
    }
    finally {
        $random.Dispose()
    }
    @(
        "POSTGRES_PASSWORD=$databasePassword"
        "JWT_SECRET=$jwtSecret"
    ) | Set-Content -LiteralPath $envFile -Encoding ascii
    Write-Host "Arquivo .env criado com segredos locais aleatórios."
}

function Test-DockerEngine {
    docker info --format '{{.ServerVersion}}' *> $null
    return $LASTEXITCODE -eq 0
}

if (-not (Test-DockerEngine)) {
    if (Test-Path -LiteralPath $desktopPath) {
        Write-Host "Iniciando Docker Desktop..."
        Start-Process -FilePath $desktopPath -WindowStyle Normal
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        throw "O Docker Engine não iniciou. Abra o Docker Desktop, aguarde ficar pronto e execute .\run-aquaflow.ps1 novamente."
    }
}

Push-Location $projectRoot
try {
    docker compose up --build
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose terminou com código $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

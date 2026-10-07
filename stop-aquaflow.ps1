$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    docker compose down
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose terminou com código $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

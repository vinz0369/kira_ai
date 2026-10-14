param(
    [string]$TestDatabase = 'kira_playwright_test',
    [string[]]$PlaywrightArgs = @()
)

$ErrorActionPreference = 'Stop'
if ($TestDatabase -ne 'kira_playwright_test') {
    throw 'Only the dedicated kira_playwright_test database is allowed.'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendDir = Join-Path $repoRoot 'backend'
$frontendDir = Join-Path $repoRoot 'frontend'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$uvicornExe = Join-Path $repoRoot '.venv\Scripts\uvicorn.exe'
$viteExe = Join-Path $repoRoot 'node_modules\.bin\vite.exe'
$priorDatabaseUrl = [Environment]::GetEnvironmentVariable('DATABASE_URL')
$priorPlaywrightBase = [Environment]::GetEnvironmentVariable('PLAYWRIGHT_BASE_URL')
$priorPlaywrightApi = [Environment]::GetEnvironmentVariable('PLAYWRIGHT_API_URL')
$priorWarnings = [Environment]::GetEnvironmentVariable('PYTHONWARNINGS')
$priorFrontendHost = [Environment]::GetEnvironmentVariable('FRONTEND_HOST')
$priorWsOrigins = [Environment]::GetEnvironmentVariable('WS_ALLOWED_ORIGINS')
$priorViteApi = [Environment]::GetEnvironmentVariable('VITE_API_URL')
$priorViteWs = [Environment]::GetEnvironmentVariable('VITE_WS_URL')
$testBackend = $null
$testFrontend = $null
$result = 1

foreach ($port in @(8001, 5174)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Isolated test port $port is already in use; refusing to interfere with it."
    }
}
if (-not (Test-Path -LiteralPath $viteExe)) { throw 'Workspace Vite executable is missing.' }

try {
    $env:PYTHONWARNINGS = 'ignore'
    Push-Location $backendDir
    try {
        $testUrl = & $pythonExe scripts/prepare_playwright_db.py
        if ($LASTEXITCODE -ne 0 -or -not $testUrl) { throw 'Could not prepare isolated Playwright database.' }
        $env:DATABASE_URL = $testUrl.Trim()
        & $pythonExe -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Isolated Playwright migration failed.' }
        & $pythonExe app/initial_data.py
        if ($LASTEXITCODE -ne 0) { throw 'Isolated Playwright seed failed.' }
    } finally {
        Pop-Location
    }

    $env:FRONTEND_HOST = 'http://127.0.0.1:5174'
    $env:WS_ALLOWED_ORIGINS = 'http://127.0.0.1:5174,http://127.0.0.1:8001'
    $testBackend = Start-Process -FilePath $uvicornExe -ArgumentList @('app.main:app', '--host', '127.0.0.1', '--port', '8001') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru
    $healthy = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8001/api/v1/utils/health-check/' -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'Isolated Playwright backend did not become healthy.' }

    $env:VITE_API_URL = 'http://127.0.0.1:8001'
    $env:VITE_WS_URL = 'ws://127.0.0.1:8001'
    $testFrontend = Start-Process -FilePath $viteExe -ArgumentList @('--host', '127.0.0.1', '--port', '5174', '--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru
    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:5174/login' -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'Isolated Playwright frontend did not become healthy.' }

    $env:PLAYWRIGHT_BASE_URL = 'http://127.0.0.1:5174'
    $env:PLAYWRIGHT_API_URL = 'http://127.0.0.1:8001'
    Push-Location $frontendDir
    try {
        & npx playwright test @PlaywrightArgs --reporter=line
        $result = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    if ($testFrontend -and -not $testFrontend.HasExited) {
        Stop-Process -Id $testFrontend.Id -ErrorAction SilentlyContinue
    }
    # The Windows vite.exe shim can exit after spawning node.exe; clean up only
    # the verified child bound to our dedicated test port.
    $frontendListener = Get-NetTCPConnection -LocalPort 5174 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($frontendListener) {
        $frontendProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($frontendListener.OwningProcess)"
        if ($frontendProcess -and $frontendProcess.CommandLine -like '*vite.js*--port 5174*') {
            Stop-Process -Id $frontendProcess.ProcessId -ErrorAction SilentlyContinue
        }
    }
    if ($testBackend -and -not $testBackend.HasExited) {
        Stop-Process -Id $testBackend.Id -ErrorAction SilentlyContinue
    }
    [Environment]::SetEnvironmentVariable('DATABASE_URL', $priorDatabaseUrl)
    [Environment]::SetEnvironmentVariable('PLAYWRIGHT_BASE_URL', $priorPlaywrightBase)
    [Environment]::SetEnvironmentVariable('PLAYWRIGHT_API_URL', $priorPlaywrightApi)
    [Environment]::SetEnvironmentVariable('PYTHONWARNINGS', $priorWarnings)
    [Environment]::SetEnvironmentVariable('FRONTEND_HOST', $priorFrontendHost)
    [Environment]::SetEnvironmentVariable('WS_ALLOWED_ORIGINS', $priorWsOrigins)
    [Environment]::SetEnvironmentVariable('VITE_API_URL', $priorViteApi)
    [Environment]::SetEnvironmentVariable('VITE_WS_URL', $priorViteWs)
}

exit $result

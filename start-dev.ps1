# SmartSketch local startup script (Windows).
#
# scripts/start-demo.sh in the repo is bash-only and was tested only on Linux.
# This is its Windows equivalent. Three Windows-specific differences it handles:
#   1. The app reads environment variables only, never the .env file, so .env is
#      loaded into the process environment here (same as `set -a; source .env`).
#   2. The worker heartbeat file defaults to the Unix path /tmp/... (see
#      app/workers/runner.py, DEFAULT_HEARTBEAT_FILE). On Windows that resolves to
#      \tmp\... and the supervisor crashes. The official WORKER_HEARTBEAT_FILE
#      override is used instead.
#   3. Backend processes must start from src\backend so that the relative
#      SQLITE_URL / STORAGE_DIR resolve to the same place as the API and worker.
#
# Prerequisites (one time):
#   - .venv created and backend dependencies installed
#   - src\frontend\node_modules installed (npm ci --prefix src\frontend)
#   - .env present (copy .env.example and fill NEO4J_PASSWORD / AUTH_JWT_SECRET)
#   - Neo4j container running: docker compose up -d neo4j
#   - Execution policy for this process:
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
#
# Usage:
#   .\start-dev.ps1                 Start API + worker + frontend
#   .\start-dev.ps1 -NoWeb          Skip the frontend
#   .\start-dev.ps1 -Migrate        Run SQLite and Neo4j migrations first
#   .\start-dev.ps1 -ImportDemo     Import the demo course after startup
#
# Stop: close the spawned windows; Neo4j: docker compose stop neo4j

param(
    [switch]$Migrate,
    [switch]$ImportDemo,
    [switch]$NoWeb
)

$ErrorActionPreference = 'Stop'

$Repo     = 'D:\SmartSketch\SmartSketch'
$Tmp      = 'D:\SmartSketch\.tmp'
$Python   = Join-Path $Repo '.venv\Scripts\python.exe'
$Backend  = Join-Path $Repo 'src\backend'
$Frontend = Join-Path $Repo 'src\frontend'
$EnvFile  = Join-Path $Repo '.env'
$LogDir   = Join-Path $Tmp 'logs'

foreach ($required in @($Python, $EnvFile, $Backend)) {
    if (-not (Test-Path $required)) { throw "Missing required path: $required" }
}
New-Item -ItemType Directory -Force -Path $Tmp, $LogDir | Out-Null

# ---- 1. Load .env literally (never execute it as a shell script) ----
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^([A-Z_][A-Z0-9_]*)=(.*)$') {
        $value = $Matches[2].Trim()
        if ($value -ne '') { Set-Item -Path "Env:$($Matches[1])" -Value $value }
    }
}
$env:TMP = $Tmp
$env:TEMP = $Tmp
$env:PYTHONPATH = $Backend
$env:WORKER_HEARTBEAT_FILE = Join-Path $Tmp 'smartsketch-worker.heartbeat'

Write-Host "LLM_MODE=$env:LLM_MODE  EMBEDDING_MODE=$env:EMBEDDING_MODE"
Write-Host "SQLITE_URL=$env:SQLITE_URL  NEO4J_URI=$env:NEO4J_URI"
Write-Host "WORKER_HEARTBEAT_FILE=$env:WORKER_HEARTBEAT_FILE"
Write-Host ''

# ---- 2. Check Neo4j ----
$neo4jUp = $false
try {
    & $Python -c "import socket; s=socket.create_connection(('127.0.0.1',7687),5); s.close()" 2>$null
    $neo4jUp = ($LASTEXITCODE -eq 0)
} catch { $neo4jUp = $false }

if ($neo4jUp) {
    Write-Host '[ok] Neo4j Bolt 7687 reachable'
} else {
    Write-Host '[!!] Neo4j is not reachable on 7687. Start it first:' -ForegroundColor Red
    Write-Host '       cd D:\SmartSketch\SmartSketch'
    Write-Host '       docker compose up -d neo4j'
    Write-Host '     Continuing; the API starts but graph features will fail.'
}

# ---- 3. Optional migrations ----
if ($Migrate) {
    Write-Host '-> SQLite migrations'
    Push-Location $Backend
    try { & $Python -m app.repositories.sqlite } finally { Pop-Location }
    Write-Host '-> Neo4j schema and vector index migrations'
    Push-Location $Backend
    try { & $Python -m app.repositories.graph_migrations } finally { Pop-Location }
    Write-Host ''
}

# ---- 4. Start API and worker in their own windows ----
function Start-BackendService {
    param([string]$Name, [string]$Module)
    $inner = "`$host.UI.RawUI.WindowTitle='SmartSketch $Name'; " +
             "Set-Location '$Backend'; " +
             "`$env:TMP='$Tmp'; `$env:TEMP='$Tmp'; " +
             "`$env:PYTHONPATH='$Backend'; " +
             "`$env:WORKER_HEARTBEAT_FILE='$env:WORKER_HEARTBEAT_FILE'; " +
             "& '$Python' -m $Module"
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $inner) | Out-Null
    Write-Host "[ok] $Name started in a new window"
}

Start-BackendService -Name 'API' -Module 'app'
Start-BackendService -Name 'worker' -Module 'app.workers'

# ---- 5. Wait for the API ----
Write-Host '-> Waiting for API'
$deadline = (Get-Date).AddSeconds(60)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3 -UseBasicParsing
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 900 }
}
if ($ready) {
    Write-Host '[ok] API ready: http://127.0.0.1:8000   (docs at /docs)'
} else {
    Write-Host '[!!] API not ready within 60s; see the API window for the traceback' -ForegroundColor Red
}

# ---- 6. Optional demo import ----
if ($ImportDemo) {
    Write-Host '-> Importing the demo course'
    Push-Location $Backend
    try { & $Python (Join-Path $Repo 'scripts\import-demo.py') } finally { Pop-Location }
}

# ---- 7. Frontend ----
if (-not $NoWeb) {
    $node = Get-Command node -ErrorAction SilentlyContinue
    $launcher = Join-Path $Frontend 'dev-server-no-config.mjs'
    if (-not $node) {
        Write-Host '[!!] node not found; skipping the frontend' -ForegroundColor Yellow
    } elseif (-not (Test-Path $launcher)) {
        Write-Host "[!!] $launcher not found; skipping the frontend" -ForegroundColor Yellow
    } else {
        $inner = "`$host.UI.RawUI.WindowTitle='SmartSketch web'; " +
                 "Set-Location '$Frontend'; & node dev-server-no-config.mjs 5173"
        Start-Process -FilePath 'powershell.exe' `
            -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $inner) | Out-Null
        Start-Sleep -Seconds 8
        Write-Host '[ok] Frontend starting: http://127.0.0.1:5173'
    }
}

Write-Host ''
Write-Host 'Demo accounts: demo_teacher / demo_student / demo_student2'
Write-Host 'Password:      smartsketch-demo'
Write-Host 'Open:          http://127.0.0.1:5173'
Write-Host 'Stop Neo4j:    cd D:\SmartSketch\SmartSketch; docker compose stop neo4j'

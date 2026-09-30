$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $env:LOCALAPPDATA 'SmartSketch-External'
$logs = Join-Path $data 'logs'
$config = Join-Path $data 'portable-config.json'
$state = Join-Path $data 'processes.json'
$python = if ($env:SMARTSKETCH_PYTHON) { $env:SMARTSKETCH_PYTHON } else { Join-Path $root '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'local-runtime.json'))) {
    $runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'local-runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = $runtime.python
    $env:JAVA_HOME = $runtime.java
    $env:NEO4J_HOME = $runtime.neo4j
}
$env:SMARTSKETCH_API_CONFIG = Join-Path $data 'api-settings.json'
$java = $env:JAVA_HOME
$neo = $env:NEO4J_HOME
$backend = Join-Path $root 'app\src\backend'
$url = 'http://localhost:18080/'
New-Item -ItemType Directory -Force -Path $data, $logs | Out-Null

function New-Secret([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}
function Test-Port([int]$port) {
    $client = New-Object Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}
function Wait-Port([int]$port, [int]$seconds, [string]$name) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-Port $port) { return }
        Start-Sleep -Seconds 1
    }
    throw "$name 未在 $seconds 秒内就绪；请查看 $logs。"
}
function Wait-Http([string]$target, [int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $target -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw "服务未就绪：$target；请查看 $logs。"
}
function Run-Step([string]$name, [string[]]$arguments) {
    Write-Host "正在$name…"
    & $python (Join-Path $backend 'portable_bootstrap.py') @arguments *> (Join-Path $logs "$name.log")
    if ($LASTEXITCODE -ne 0) { throw "$name 失败；请查看 $logs\$name.log。" }
}
function Start-Managed([string]$name, [string]$file, [string]$arguments, [int]$order) {
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $backend `
        -RedirectStandardOutput (Join-Path $logs "$name.log") `
        -RedirectStandardError (Join-Path $logs "$name-error.log") `
        -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 400
    $started = Get-Process -Id $process.Id
    $created = [string]$started.StartTime.ToFileTimeUtc()
    $script:managed += [pscustomobject]@{ name=$name; pid=$process.Id; created=$created; executable=$file; order=$order }
    $script:managed | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $state -Encoding UTF8
    return $process
}
function Stop-Managed {
    if ($script:ownsProcesses -and (Test-Path -LiteralPath $state)) {
        & (Join-Path $PSScriptRoot 'stop.ps1')
    }
}

try {
    if (-not (Test-Path -LiteralPath $python)) { throw "找不到 Python 3.12 虚拟环境：$python。请按使用手册安装。" }
    if (-not $java -or -not (Test-Path -LiteralPath (Join-Path $java 'bin\java.exe'))) { throw '未找到 JAVA_HOME 指向的 Java 17；请按使用手册配置。' }
    if (-not $neo -or -not (Test-Path -LiteralPath (Join-Path $neo 'lib'))) { throw '未找到 NEO4J_HOME 指向的 Neo4j 5.26.31；请按使用手册配置。' }
    $release = Join-Path $java 'release'
    if (-not (Test-Path -LiteralPath $release) -or -not (Select-String -LiteralPath $release -Pattern '^JAVA_VERSION="17\.' -Quiet)) {
        throw 'JAVA_HOME 必须指向 Java 17 运行环境。'
    }
    $javaExe = Join-Path $java 'bin\java.exe'
    $neoVersion = & $javaExe -cp (Join-Path $neo 'lib\*') "-Dbasedir=$neo" org.neo4j.server.startup.Neo4jAdminCommand --version
    if ($LASTEXITCODE -ne 0 -or ($neoVersion | Out-String).Trim() -ne '5.26.31') {
        throw 'NEO4J_HOME 必须指向 Neo4j Community 5.26.31。'
    }
    if (-not (Get-ChildItem -LiteralPath (Join-Path $neo 'plugins') -Filter 'apoc-*-core.jar' -ErrorAction SilentlyContinue)) {
        throw 'Neo4j plugins 中缺少 APOC Core JAR；请按使用手册从 labs 复制。'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'app\web\index.html'))) { throw '软件文件不完整：缺少前端 index.html。' }
    & $python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.12；请按使用手册建立虚拟环境。' }
    & $python -c 'import fastapi, neo4j, pdfminer, uvicorn' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Python 依赖未安装；请在解压目录运行 .\.venv\Scripts\python.exe -m pip install -r requirements.txt。' }
    $env:PYTHONPATH = $backend
    if (Test-Path -LiteralPath $state) {
        $old = @(Get-Content -LiteralPath $state -Raw | ConvertFrom-Json)
        $live = @($old | Where-Object { Get-Process -Id $_.pid -ErrorAction SilentlyContinue })
        if ($live.Count -gt 0) {
            Write-Host "智绘学途已在运行：$url"
            if ($env:SMARTSKETCH_NO_OPEN -ne '1') { Start-Process $url }
            exit 0
        }
        Remove-Item -LiteralPath $state -Force
    }
    foreach ($port in @(17687, 17474, 18080)) {
        if (Test-Port $port) { throw "本机端口 $port 已被占用；关闭占用程序后重试。" }
    }
    if (-not (Test-Path -LiteralPath $config)) {
        @{ neo4jPassword=(New-Secret 24); jwtSecret=(New-Secret 48) } |
            ConvertTo-Json | Set-Content -LiteralPath $config -Encoding UTF8
    }
    $secrets = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    $env:JAVA_HOME = $java
    $env:PATH = (Join-Path $java 'bin') + ';' + $env:PATH
    $env:NEO4J_HOME = $neo
    $env:NEO4J_CONF = Join-Path $data 'neo4j-conf'
    New-Item -ItemType Directory -Force -Path $env:NEO4J_CONF | Out-Null
    $neoConf = @(
        'server.default_listen_address=127.0.0.1',
        'server.bolt.listen_address=127.0.0.1:17687',
        'server.http.listen_address=127.0.0.1:17474',
        'server.https.enabled=false',
        "server.directories.data=$((Join-Path $data 'neo4j-data').Replace('\', '/'))",
        "server.directories.logs=$((Join-Path $logs 'neo4j').Replace('\', '/'))",
        'dbms.security.procedures.unrestricted=apoc.*'
    )
    $neoConf | Set-Content -LiteralPath (Join-Path $env:NEO4J_CONF 'neo4j.conf') -Encoding ASCII
    $env:NEO4J_AUTH = ''
    $passwordMarker = Join-Path $data 'neo4j-password-initialized'
    if (-not (Test-Path -LiteralPath $passwordMarker)) {
        & $javaExe -cp (Join-Path $neo 'lib\*') "-Dbasedir=$neo" org.neo4j.server.startup.Neo4jAdminCommand dbms set-initial-password $secrets.neo4jPassword *> (Join-Path $logs 'neo4j-init.log')
        if ($LASTEXITCODE -ne 0) { throw "Neo4j 初始口令设置失败；请查看 $logs\neo4j-init.log。" }
        New-Item -ItemType File -Path $passwordMarker | Out-Null
    }
    $env:APP_ENV = 'development'
    $env:API_HOST = '127.0.0.1'
    $env:API_PORT = '18080'
    $env:WEB_ORIGIN = $url.TrimEnd('/')
    $env:SMARTSKETCH_WEB_DIST = Join-Path $root 'app\web'
    $env:SQLITE_URL = 'sqlite:///' + (Join-Path $data 'smartsketch.sqlite3').Replace('\', '/')
    $env:STORAGE_DIR = Join-Path $data 'storage'
    $env:NEO4J_URI = 'bolt://127.0.0.1:17687'
    $env:NEO4J_USER = 'neo4j'
    $env:NEO4J_PASSWORD = $secrets.neo4jPassword
    $env:AUTH_JWT_SECRET = $secrets.jwtSecret
    $env:LLM_MODE = 'demo'
    $env:EMBEDDING_MODE = 'demo'
    $env:QA_SIMILARITY_THRESHOLD = '0.58'
    $env:SEED_DEMO_PASSWORD = 'smartsketch-demo'
    $env:WORKER_HEARTBEAT_FILE = Join-Path $data 'worker.heartbeat'
    $script:managed = @()
    Write-Host '正在启动 Neo4j…'
    $neoArgs = '-cp "' + (Join-Path $neo 'lib\*') + '" "-Dbasedir=' + $neo + '" org.neo4j.server.startup.Neo4jCommand console'
    $neoProcess = Start-Managed 'neo4j' $javaExe $neoArgs 1
    $script:ownsProcesses = $true
    Wait-Port 17687 120 'Neo4j'
    Run-Step 'sqlite-migrate' @('-m', 'app.repositories.sqlite')
    Run-Step 'neo4j-migrate' @('-m', 'app.repositories.graph_migrations')
    Run-Step 'seed' @((Join-Path $root 'app\scripts\seed-demo-accounts.py'))
    $api = Start-Managed 'api' $python 'portable_bootstrap.py -m uvicorn app.portable_web:app --host 127.0.0.1 --port 18080' 2
    $worker = Start-Managed 'worker' $python 'portable_bootstrap.py -m app.workers' 3
    Wait-Http 'http://127.0.0.1:18080/health' 60
    Wait-Http $url 10
    Write-Host '检查并导入演示课程（首次可能需要几分钟）…'
    Run-Step 'import' @((Join-Path $root 'app\scripts\import-demo.py'))
    if ($env:SMARTSKETCH_NO_OPEN -ne '1') { Start-Process $url }
    Write-Host "已启动：$url"
    Write-Host '账号：demo_teacher / demo_student / demo_student2；密码：smartsketch-demo'
    Write-Host '结束使用时请双击“停止智绘学途.cmd”。'
    while (-not $api.HasExited -and -not $worker.HasExited -and -not $neoProcess.HasExited) {
        Start-Sleep -Seconds 2
        $api.Refresh(); $worker.Refresh(); $neoProcess.Refresh()
    }
    Write-Warning "有服务退出；请查看 $logs。"
} catch {
    Write-Error $_
    exit 1
} finally {
    Stop-Managed
}

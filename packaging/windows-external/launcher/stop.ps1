$ErrorActionPreference = 'Stop'
$state = Join-Path $env:LOCALAPPDATA 'SmartSketch-External\processes.json'
if (-not (Test-Path -LiteralPath $state)) {
    Write-Host '智绘学途没有由本压缩包启动的进程。'
    exit 0
}
$processes = Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
foreach ($entry in @($processes) | Sort-Object -Property order -Descending) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    # PID may be reused; both creation time and configured executable must match.
    $created = [string]$process.StartTime.ToFileTimeUtc()
    if ($created -ne $entry.created -or [IO.Path]::GetFullPath($process.Path) -ne [IO.Path]::GetFullPath($entry.executable)) {
        Write-Warning "跳过 PID $($entry.pid)：进程身份已变化。"
        continue
    }
    & taskkill.exe /PID $entry.pid /T /F | Out-Null
    Write-Host "已停止 $($entry.name)。"
}
Remove-Item -LiteralPath $state -Force
Write-Host '已停止智绘学途；课程数据仍保存在本机。'

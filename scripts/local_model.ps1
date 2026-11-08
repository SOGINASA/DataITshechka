param(
    [ValidateSet('setup', 'start', 'restart', 'status', 'stop')][string]$Action = 'status',
    [string]$Model = 'qwen3:8b',
    [ValidateSet('f16', 'q8_0', 'q4_0')][string]$CacheType = 'q8_0'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolRoot = Join-Path $projectRoot '.tools'
$executable = Join-Path $toolRoot 'ollama\ollama.exe'
$pidFile = Join-Path $toolRoot 'ollama.pid'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = Join-Path $toolRoot 'ollama-models'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = $CacheType

function Get-LocalOllama {
    try { return Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 }
    catch { return $null }
}

if ($Action -in @('stop','restart')) {
    if (Test-Path -LiteralPath $pidFile) {
        $processId = [int](Get-Content -LiteralPath $pidFile)
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process -and $process.Path -eq $executable) { Stop-Process -Id $processId }
        Remove-Item -LiteralPath $pidFile
    }
    if ($Action -eq 'stop') { exit }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-LocalOllama)) { break }
        Start-Sleep -Milliseconds 250
    }
}
if ($Action -eq 'setup') {
    & python (Join-Path $PSScriptRoot 'install_ollama.py')
    if ($LASTEXITCODE -ne 0) { throw 'Ollama installation failed' }
}
if ($Action -in @('setup','start','restart')) {
    if (-not (Test-Path -LiteralPath $executable)) { throw 'Run this script with -Action setup first' }
    if (-not (Get-LocalOllama)) {
        $process = Start-Process -FilePath $executable -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $toolRoot 'ollama.stdout.log') `
            -RedirectStandardError (Join-Path $toolRoot 'ollama.stderr.log')
        $process.Id | Set-Content -LiteralPath $pidFile
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if (Get-LocalOllama) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not (Get-LocalOllama)) { throw 'Ollama did not start; inspect .tools/ollama.stderr.log' }
        @{ flash_attention = $true; kv_cache_type = $CacheType; process_id = $process.Id } |
            ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $toolRoot 'ollama-runtime.json')
    }
}
if ($Action -eq 'setup') {
    & $executable pull $Model
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
}
if (Get-LocalOllama) {
    Invoke-RestMethod 'http://127.0.0.1:11434/api/version'
    Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' | ConvertTo-Json -Depth 5
} else { Write-Output 'Ollama is stopped. Run scripts/local_model.ps1 -Action start' }

param([switch]$Main)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
Push-Location $taskRoot
try {
    $taskFiles = @('compose.yaml', 'compose.dev.yaml')
    if (-not $Main -and -not $env:BGE_MODEL_PATH) {
        $env:BGE_MODEL_PATH = Join-Path $env:USERPROFILE '.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'
    }
    if ($Main) { $taskFiles = @('compose.yaml', '.env.compose-ui.yaml', '.env.join-v1.yaml') }
    $taskArguments = @('backend/scripts/verify_runtime.py')
    foreach ($taskFile in $taskFiles) { $taskArguments += @('--compose-file', $taskFile) }
    & "$taskRoot/backend/.venv/Scripts/python.exe" @taskArguments
    if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed.' }
} finally { Pop-Location }

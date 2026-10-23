param([switch]$Build, [string]$ModelPath = $env:BGE_MODEL_PATH, [switch]$Gpu)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
if (-not $ModelPath) {
    $ModelPath = Join-Path $env:USERPROFILE '.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'
}
if (-not (Test-Path -LiteralPath (Join-Path $ModelPath 'model.safetensors'))) {
    throw 'Verified BGE snapshot is missing. No download will be attempted.'
}
$env:BGE_MODEL_PATH = (Resolve-Path -LiteralPath $ModelPath).Path
Push-Location $taskRoot
try {
    $taskCompose = @('compose', '-p', 'shopquery-ai', '-f', 'compose.yaml', '-f', 'compose.dev.yaml')
    if ($Gpu) { $taskCompose += @('-f', 'compose.gpu.yaml') }
    $taskConfigText = & docker @taskCompose config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed.' }
    $taskConfig = $taskConfigText | ConvertFrom-Json
    if ($taskConfig.volumes.postgres_dev.name -ne 'shopquery-ai_postgres_dev_stage1' -or
        $taskConfig.services.api.environment.DATABASE_SETUP_URL -notmatch '@devdb:5432/shopquery_dev$' -or
        $taskConfig.services.api.environment.BETA_PROVIDER_DATA_ENABLED -ne 'false' -or
        $taskConfig.services.api.environment.GUEST_AI_ENABLED -ne 'false') {
        throw 'Development database/provider isolation failed.'
    }
    $taskExisting = & docker ps -q --filter name=^/shopquery-ai-api-1$
    if ($taskExisting) {
        $taskRunning = (& docker inspect $taskExisting | ConvertFrom-Json)[0]
        $taskDatabase = $taskRunning.Config.Env | Where-Object { $_ -like 'DATABASE_SETUP_URL=*' }
        if ($taskDatabase -match '@db:5432/shopquery$') {
            $taskLeases = & docker exec shopquery-ai-db-1 psql -U shopquery_setup -d shopquery -At -c "SELECT count(*) FROM resource_leases WHERE expires_at>now();"
            if ($LASTEXITCODE -ne 0 -or [int]$taskLeases -gt 0) {
                throw 'Main has active work or its activity could not be verified.'
            }
            $taskProcesses = & docker top $taskExisting -eo pid,ppid,args
            if ($LASTEXITCODE -ne 0 -or ($taskProcesses -match 'spawn_main|multiprocessing')) {
                throw 'Guest work is running or process activity could not be verified.'
            }
        } elseif ($taskDatabase -notmatch '@devdb:5432/shopquery_dev$') {
            throw 'Unexpected active API database; inspect runtime before switching.'
        }
    }
    & docker @taskCompose up -d --no-deps --wait devdb
    if ($LASTEXITCODE -ne 0) { throw 'Development PostgreSQL did not become healthy.' }
    $taskBuildFlag = @()
    if ($Build) { $taskBuildFlag = @('--build') }
    & docker @taskCompose up -d --no-deps --wait @taskBuildFlag api web
    if ($LASTEXITCODE -ne 0) { throw 'Development API/web did not become healthy.' }
    & docker @taskCompose exec -T api python scripts/setup_database.py --confirm-database shopquery_dev --fresh
    if ($LASTEXITCODE -ne 0) { throw 'Fresh development schema setup failed.' }
    Write-Output '8080: DEVELOPMENT, isolated shopquery_dev database, paid AI disabled.'
} finally { Pop-Location }

param(
    [switch]$Deploy,
    [ValidateSet('all', 'api', 'web')][string]$Service = 'all',
    [string]$ConfigPath = '.env.release',
    [switch]$Gpu,
    [switch]$Observability
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
Push-Location $taskRoot
try {
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw 'Reviewed release environment file is missing.'
    }
    $taskFiles = @('compose.yaml', '.env.compose-ui.yaml', '.env.join-v1.yaml', 'compose.release.yaml')
    if ($Gpu) { $taskFiles += 'compose.release.gpu.yaml' }
    if ($Observability) { $taskFiles += 'ops/langfuse/shopquery.compose.yaml' }
    $taskCompose = @('compose', '-p', 'shopquery-ai', '--env-file', '.env', '--env-file', $ConfigPath)
    foreach ($taskFile in $taskFiles) { $taskCompose += @('-f', $taskFile) }
    $taskText = & docker @taskCompose config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Release configuration could not be resolved.' }
    $taskConfig = $taskText | ConvertFrom-Json
    if ($taskConfig.volumes.postgres_data.name -ne 'shopquery-ai_postgres_auth_20261019' -or
        -not $taskConfig.volumes.postgres_data.external -or
        $taskConfig.services.api.environment.DATABASE_SETUP_URL -notmatch '@db:5432/shopquery$' -or
        $taskConfig.services.PSObject.Properties.Name -contains 'devdb') {
        throw 'Release must use the protected main database, without DevDB.'
    }
    foreach ($taskName in @('api', 'web')) {
        $taskDefinition = $taskConfig.services.$taskName
        if ($taskDefinition.image -notmatch '^.+@sha256:[0-9a-f]{64}$' -or $taskDefinition.build) {
            throw 'Release requires existing immutable image digests; no build is allowed.'
        }
        $taskImage = (& docker image inspect $taskDefinition.image | ConvertFrom-Json)[0]
        if ($LASTEXITCODE -ne 0 -or
            $taskImage.Config.Labels.'org.opencontainers.image.revision' -notmatch '^[0-9a-f]{40}$') {
            throw 'Release image is unavailable or lacks source identity.'
        }
        $taskCommand = $taskImage.Config.Cmd
        if ($taskDefinition.command) { $taskCommand = $taskDefinition.command }
        if ($taskCommand -contains '--reload' -or
            @($taskDefinition.volumes | Where-Object { $_.target -like '/app*' }).Count -gt 0) {
            throw 'Development source mounts or reload are not allowed in release.'
        }
        if ($taskName -eq 'api' -and
            ($taskCommand -notcontains '--workers' -or
             $taskCommand[[Array]::IndexOf($taskCommand, '--workers') + 1] -ne '1')) {
            throw 'Release requires one explicit API worker.'
        }
        $taskPublished = '8001'
        if ($taskName -eq 'web') { $taskPublished = '8080' }
        if (@($taskDefinition.ports).Count -ne 1 -or
            $taskDefinition.ports[0].published -ne $taskPublished -or
            $taskDefinition.ports[0].host_ip -ne '127.0.0.1') {
            throw 'Release ports must remain loopback API8001 and Web8080.'
        }
        $taskSourcePaths = @('frontend/src', 'frontend/index.html', 'frontend/vite.config.ts',
            'frontend/tsconfig.json', 'frontend/package.json', 'frontend/package-lock.json',
            'frontend/Dockerfile', 'infrastructure/nginx')
        if ($taskName -eq 'api') {
            $taskSourcePaths = @('backend/app', 'backend/pyproject.toml', 'backend/uv.lock', 'backend/Dockerfile', 'data')
        }
        & git diff --quiet $taskImage.Config.Labels.'org.opencontainers.image.revision' -- @taskSourcePaths
        if ($LASTEXITCODE -ne 0) { throw 'Release image source differs from the workspace.' }
    }
    if ($Deploy) {
        & "$PSScriptRoot/invoke-python.ps1" -PythonArguments @('-c', 'import select, subprocess')
        if ($LASTEXITCODE -ne 0) { throw 'Runtime verifier dependencies are BLOCKED; no cutover performed.' }
        $taskRunning = & docker ps -q --filter name=^/shopquery-ai-api-1$
        if ($taskRunning) {
            $taskCurrent = (& docker inspect $taskRunning | ConvertFrom-Json)[0]
            $taskDatabase = $taskCurrent.Config.Env | Where-Object { $_ -like 'DATABASE_SETUP_URL=*' }
            $taskDbContainer = 'shopquery-ai-db-1'
            $taskDbName = 'shopquery'
            if ($taskDatabase -match '@devdb:5432/shopquery_dev$') {
                $taskDbContainer = 'shopquery-ai-devdb-1'
                $taskDbName = 'shopquery_dev'
            } elseif ($taskDatabase -notmatch '@db:5432/shopquery$') {
                throw 'Unknown active API database; inspect before promotion.'
            }
            $taskLeases = & docker exec $taskDbContainer psql -XAt -U shopquery_setup -d $taskDbName -c 'SELECT count(*) FROM resource_leases WHERE expires_at>now();'
            if ($LASTEXITCODE -ne 0 -or [int]$taskLeases -ne 0) {
                throw 'Active work exists or could not be verified.'
            }
            $taskProcesses = & docker top $taskRunning -eo pid,ppid,args
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Guest workers.' }
            $taskAllowedSpawn = 0
            if ($taskCurrent.Config.Cmd -contains '--reload') { $taskAllowedSpawn = 1 }
            if (@($taskProcesses | Where-Object { $_ -match 'spawn_main' }).Count -gt $taskAllowedSpawn) {
                throw 'Guest work may be running; retry in the approved maintenance window.'
            }
        }
        $taskNames = @('api', 'web')
        if ($Service -ne 'all') { $taskNames = @($Service) }
        foreach ($taskName in $taskNames) {
            & docker @taskCompose up -d --no-deps --no-build --pull never --wait --wait-timeout 180 $taskName
            if ($LASTEXITCODE -ne 0) { throw "Release $taskName did not become healthy; use the reviewed rollback." }
        }
        if ($Service -eq 'api') {
            & docker @taskCompose exec -T web nginx -t
            if ($LASTEXITCODE -ne 0) { throw 'Web proxy configuration validation failed.' }
            & docker @taskCompose exec -T web nginx -s reload
            if ($LASTEXITCODE -ne 0) { throw 'Web proxy could not refresh the API address.' }
        }
    }
    $taskArguments = @('backend/scripts/verify_runtime.py', '--env-file', '.env', '--env-file', $ConfigPath)
    foreach ($taskFile in $taskFiles) { $taskArguments += @('--compose-file', $taskFile) }
    & "$PSScriptRoot/invoke-python.ps1" -PythonArguments $taskArguments
    if ($LASTEXITCODE -ne 0) { throw 'Runtime source/image/environment verification failed.' }
} finally { Pop-Location }

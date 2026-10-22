param([switch]$Integration, [string[]]$Tests = @())
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskKeys = @('DATABASE_SETUP_URL', 'DATABASE_READONLY_URL', 'SHOPQUERY_TEST_DATABASE_URL',
              'RUN_DATABASE_TESTS', 'GEMINI_API_KEY', 'INETCLOUD_BASE_URL',
              'AI_GEMINI_FALLBACK_ENABLED', 'SQL_JOIN_V1_ENABLED')
$taskSaved = @{}
foreach ($taskKey in $taskKeys) { $taskSaved[$taskKey] = [Environment]::GetEnvironmentVariable($taskKey) }
Push-Location "$taskRoot/backend"
try {
    $env:GEMINI_API_KEY = ''
    $env:INETCLOUD_BASE_URL = ''
    $env:AI_GEMINI_FALLBACK_ENABLED = 'false'
    $env:SQL_JOIN_V1_ENABLED = 'false'
    $env:DATABASE_SETUP_URL = 'postgresql+psycopg://shopquery_setup:setup_password@127.0.0.1:15433/shopquery_test_stage1'
    $env:DATABASE_READONLY_URL = 'postgresql+psycopg://shopquery_reader:readonly_password@127.0.0.1:15433/shopquery_test_stage1'
    $env:SHOPQUERY_TEST_DATABASE_URL = $env:DATABASE_SETUP_URL
    $env:RUN_DATABASE_TESTS = '0'
    $taskMarker = 'not integration and not live'
    if ($Integration) {
        $env:DATABASE_SETUP_URL = 'postgresql+psycopg://shopquery_setup:setup_password@127.0.0.1:15433/shopquery_test_stage1'
        $env:DATABASE_READONLY_URL = 'postgresql+psycopg://shopquery_reader:readonly_password@127.0.0.1:15433/shopquery_test_stage1'
        $env:SHOPQUERY_TEST_DATABASE_URL = $env:DATABASE_SETUP_URL
        $env:RUN_DATABASE_TESTS = '1'
        $taskMarker = 'integration and not live'
    }
    & "$taskRoot/backend/.venv/Scripts/python.exe" -m pytest -m $taskMarker @Tests -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Offline tests failed.' }
} finally {
    foreach ($taskKey in $taskKeys) {
        if ($null -eq $taskSaved[$taskKey]) {
            Remove-Item -LiteralPath "Env:$taskKey" -ErrorAction SilentlyContinue
        } else { [Environment]::SetEnvironmentVariable($taskKey, $taskSaved[$taskKey]) }
    }
    Pop-Location
}

param([Parameter(Mandatory = $true)][string[]]$PythonArguments)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskStart = [System.Diagnostics.ProcessStartInfo]::new()
$taskStart.FileName = Join-Path $taskRoot 'backend/.venv/Scripts/python.exe'
$taskStart.WorkingDirectory = (Get-Location).Path
$taskStart.UseShellExecute = $false
$taskStart.CreateNoWindow = $true
$taskStart.RedirectStandardOutput = $true
$taskStart.RedirectStandardError = $true
$taskStart.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$taskStart.StandardErrorEncoding = [System.Text.Encoding]::UTF8
if ($taskStart.PSObject.Properties.Name -contains 'ArgumentList') {
    foreach ($taskArgument in $PythonArguments) { $taskStart.ArgumentList.Add($taskArgument) }
} else {
    $taskQuoted = foreach ($taskArgument in $PythonArguments) {
        # Windows argv quoting, without introducing a second shell.
        '"' + [regex]::Replace([regex]::Replace($taskArgument, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
    }
    $taskStart.Arguments = $taskQuoted -join ' '
}
$taskProcess = [System.Diagnostics.Process]::new()
$taskProcess.StartInfo = $taskStart
try {
    if (-not $taskProcess.Start()) { throw 'Project Python did not start.' }
    $taskStdout = $taskProcess.StandardOutput.ReadToEndAsync()
    $taskStderr = $taskProcess.StandardError.ReadToEndAsync()
    $taskProcess.WaitForExit()
    [Console]::Out.Write($taskStdout.GetAwaiter().GetResult())
    [Console]::Error.Write($taskStderr.GetAwaiter().GetResult())
    exit $taskProcess.ExitCode
} catch {
    throw "Project Python execution BLOCKED/FAILED; no interpreter fallback was attempted. $($_.Exception.Message)"
} finally { $taskProcess.Dispose() }

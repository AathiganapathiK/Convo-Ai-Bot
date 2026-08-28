$env:BROWSER = "none"
$env:PORT = "3005"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "[0.00s] Executing 'npm start' on PORT 3005..."

$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = "cmd.exe"
$pinfo.Arguments = "/c npm start"
$pinfo.WorkingDirectory = "d:\RR_Bot\Convo-Ai-Bot\frontend"
$pinfo.UseShellExecute = $false
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $pinfo
$process.Start() | Out-Null

while (-not $process.StandardOutput.EndOfStream) {
    $line = $process.StandardOutput.ReadLine()
    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 2)
    Write-Host "[$elapsed`s] $line"
    if ($line -match "Compiled successfully" -or $line -match "Local:" -or $line -match "Compiled with warnings" -or $line -match "webpack compiled") {
        Write-Host ""
        Write-Host ">>> READY IN $elapsed SECONDS <<<"
        Write-Host ""
        break
    }
}

try {
    $process.Kill()
} catch {}

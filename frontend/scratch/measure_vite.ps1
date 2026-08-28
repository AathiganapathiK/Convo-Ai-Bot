$env:BROWSER = "none"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host "[0.00s] Executing 'npm run dev' (Vite dev server)..."

$pinfo = New-Object System.Diagnostics.ProcessStartInfo
$pinfo.FileName = "cmd.exe"
$pinfo.Arguments = "/c npm run dev"
$pinfo.WorkingDirectory = "d:\RR_Bot\Convo-Ai-Bot\frontend"
$pinfo.UseShellExecute = $false
$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $pinfo
$process.Start() | Out-Null

$serverReadyTime = $null

while (-not $process.StandardOutput.EndOfStream) {
    $line = $process.StandardOutput.ReadLine()
    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 2)
    Write-Host "[$elapsed`s] $line"
    if ($line -match "ready in" -or $line -match "Local:" -or $line -match "Network:") {
        if ($null -eq $serverReadyTime) {
            $serverReadyTime = $elapsed
            Write-Host ""
            Write-Host ">>> VITE DEV SERVER READY AT $serverReadyTime SECONDS <<<"
            Write-Host ""
            break
        }
    }
}

# Test HTTP response time from localhost:3000
$tHttpStart = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5
    $httpTime = [math]::Round($tHttpStart.Elapsed.TotalSeconds, 2)
    Write-Host ">>> LOCALHOST RESPONDED IN $httpTime SECONDS (Status $($resp.StatusCode)) <<<"
} catch {
    Write-Host ">>> Localhost request failed: $_ <<<"
}

try {
    $process.Kill()
} catch {}

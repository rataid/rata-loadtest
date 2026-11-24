# Run Locust locally in Docker with one test's locustfile.py.
# Then open http://localhost:8089 in the browser.
#
#   .\run-local.ps1                                  default test (stl-presign-upload), newest Locust
#   .\run-local.ps1 -Test stl-presign-upload         pick a test folder under tests/
#   .\run-local.ps1 -Version 2.47.0                  a specific Locust version (use the one on the VM)
#   .\run-local.ps1 -Detach                          run in the background; stop: docker stop rata-locust-local
#   .\run-local.ps1 --class-picker                   extra Locust options go at the end (long form)
#
# A local run is for rehearsal only (1 user, small values). Real load tests run on the
# Locust VM in Singapore, because from a laptop the results are limited by your internet.
param(
  [string]$Test = "stl-presign-upload",
  [string]$Version = "latest",
  [int]$Port = 8089,
  [switch]$Detach,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$LocustArgs
)

$testDir = Join-Path $PSScriptRoot "tests\$Test"
if (-not (Test-Path (Join-Path $testDir "locustfile.py"))) {
  Write-Error "No locustfile.py in tests\$Test"
  exit 1
}

$name = "rata-locust-local"

# Remove a previous run that is still around, so the name and port are free.
docker rm -f $name 2>$null | Out-Null

$mode = if ($Detach) { "-d" } else { "-it" }

Write-Host "Test: $Test"
Write-Host "Locust dashboard: http://localhost:$Port"
if ($Detach) {
  Write-Host "Running in the background. Stop it with: docker stop $name"
} else {
  Write-Host "Press Ctrl+C to stop."
}

docker run --rm $mode --name $name -p "${Port}:8089" -v "${testDir}:/mnt/locust" "locustio/locust:$Version" -f /mnt/locust/locustfile.py @LocustArgs

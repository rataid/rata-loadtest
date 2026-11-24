# Run a test's dry run (tests/<name>/_dryrun_test.py) inside the official Locust image.
# The dry run talks only to a fake server on 127.0.0.1 inside the container: nothing reaches sandbox.
#
#   .\tools\dryrun.ps1 -Test stl-presign-upload
#   .\tools\dryrun.ps1 -Test stl-presign-upload -Version 2.47.0      same Locust version as the VM
#   .\tools\dryrun.ps1 -Test stl-presign-upload stop hang            only some scenarios
param(
  [Parameter(Mandatory = $true)][string]$Test,
  [string]$Version = "latest",
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Scenarios
)

$testDir = Join-Path (Split-Path $PSScriptRoot -Parent) "tests\$Test"
if (-not (Test-Path (Join-Path $testDir "_dryrun_test.py"))) {
  Write-Error "No _dryrun_test.py in tests\$Test"
  exit 1
}

# --network none: the container has no network access except its own 127.0.0.1
docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -v "${testDir}:/mnt/locust" --entrypoint python "locustio/locust:$Version" /mnt/locust/_dryrun_test.py @Scenarios
exit $LASTEXITCODE

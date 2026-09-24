# run_eval_gate.ps1 -- the manual accuracy gate until CI exists (evals/README.md).
# One-command wrapper: restarts the backend container, waits for it to come up, then
# runs the golden set through the LIVE agent inside the container
# (evals/run_gate.py) and propagates its exit code.
#
# Usage:
#   .\run_eval_gate.ps1 -SourceId 2 -Golden evals/golden/maps.jsonl -MinAccuracy 0.6
#   .\run_eval_gate.ps1 -SourceId 2 -Golden evals/golden/maps.jsonl -ValueVerified
#
# Exit codes (evals/run_gate.py's, propagated unchanged):
#   0 -- strict accuracy >= -MinAccuracy
#   1 -- strict accuracy below -MinAccuracy
#   2 -- malformed input (bad golden file, bad --source-id, etc.)
#
# Runtime: roughly 20 minutes for the 25-question maps.jsonl golden set --
# the ask-loop is sequential and each question is a real LLM round trip.
param(
    [Parameter(Mandatory = $true)][int]$SourceId,
    [string]$Golden = "evals/golden/maps.jsonl",
    [double]$MinAccuracy = 0.5,
    [string]$Out = "/tmp/eval_gate_results.json",
    [switch]$ValueVerified
)

Write-Host "Restarting backend container..."
docker compose restart backend
Write-Host "Waiting for backend to come up..."
Start-Sleep -Seconds 8

$gateArgs = @(
    "-m", "evals.run_gate",
    "--source-id", $SourceId,
    "--golden", $Golden,
    "--min-accuracy", $MinAccuracy,
    "--out", $Out
)
if ($ValueVerified) { $gateArgs += "--value-verified" }

docker exec datalytics_backend python @gateArgs
exit $LASTEXITCODE

param(
    [switch]$Apply,
    [int]$BatchSize = 64,
    [string]$Collection = "course_material_chunks_v1_1_cosine"
)

$ErrorActionPreference = "Stop"
$BackendRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
$Script = Join-Path $PSScriptRoot "rebuild_cosine_vectors.py"

$Arguments = @($Script, "--batch-size", $BatchSize, "--collection", $Collection)
if ($Apply) {
    $Arguments += @("--apply", "--yes")
}

& $Python @Arguments
exit $LASTEXITCODE

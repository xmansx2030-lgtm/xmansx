param(
    [ValidateSet("login", "teacher", "dashboard", "student_profile", "device_events", "counselor", "platform", "pdf", "mixed")]
    [string]$Profile,
    [ValidateRange(1, 2000)]
    [int]$Users,
    [ValidateRange(0.1, 1000)]
    [double]$SpawnRate,
    [ValidatePattern("^[0-9]+[smh]$")]
    [string]$RunTime,
    [string]$BaseUrl = "http://localhost:58005",
    [string]$DataFile = "phase19-data.json",
    [string]$ResultName = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$locust = Join-Path $root "backend\.venv\Scripts\locust.exe"
$locustFile = Join-Path $root "loadtests\locustfile.py"
$dataPath = (Resolve-Path (Join-Path $root $DataFile)).Path
$resultDir = Join-Path $root "phase19-results"
New-Item -ItemType Directory -Force $resultDir | Out-Null

if (-not $ResultName) {
    $ResultName = "$Profile-u$Users"
}
$resultPrefix = Join-Path $resultDir $ResultName
$env:PHASE19_PROFILE = $Profile
$env:PHASE19_DATA_FILE = $dataPath

& $locust -f $locustFile --headless -u $Users -r $SpawnRate -t $RunTime `
    --host $BaseUrl --csv $resultPrefix --only-summary
exit $LASTEXITCODE

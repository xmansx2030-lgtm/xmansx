param(
    [ValidateRange(1, 7200)]
    [int]$DurationSeconds,
    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 5,
    [string]$ResultName = "metrics"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$resultDir = Join-Path $root "phase19-results"
New-Item -ItemType Directory -Force $resultDir | Out-Null
$output = Join-Path $resultDir "$ResultName.csv"
$containers = @(
    "xmansx-phase19-final-postgres-1",
    "xmansx-phase19-final-redis-1",
    "xmansx-phase19-final-backend-1",
    "xmansx-phase19-final-worker-1",
    "xmansx-phase19-final-beat-1",
    "xmansx-phase19-final-frontend-1"
)
$rows = @()
$deadline = (Get-Date).AddSeconds($DurationSeconds)
while ((Get-Date) -lt $deadline) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("o")
    $stats = docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}" @containers
    $pg = docker exec xmansx-phase19-final-postgres-1 psql `
        -U xmansx_phase19 -d xmansx_phase19 -Atc `
        "select count(*) || ',' || count(*) filter (where state='active') from pg_stat_activity; select deadlocks from pg_stat_database where datname=current_database();"
    $redisInfo = docker exec xmansx-phase19-final-redis-1 redis-cli INFO memory clients
    $usedMemory = ($redisInfo | Select-String "^used_memory:").Line.Split(":")[1].Trim()
    $clients = ($redisInfo | Select-String "^connected_clients:").Line.Split(":")[1].Trim()
    $queueDepth = docker exec xmansx-phase19-final-redis-1 redis-cli LLEN celery
    $connectionParts = $pg[0].Split(",")
    foreach ($line in $stats) {
        $parts = $line.Split("|")
        $rows += [pscustomobject]@{
            timestamp = $timestamp
            container = $parts[0]
            cpu_percent = $parts[1]
            memory = $parts[2]
            db_connections = $connectionParts[0]
            db_active = $connectionParts[1]
            db_deadlocks = $pg[1]
            redis_used_bytes = $usedMemory
            redis_clients = $clients
            celery_queue_depth = $queueDepth
        }
    }
    Start-Sleep -Seconds $IntervalSeconds
}
$rows | Export-Csv -NoTypeInformation -Encoding utf8 $output
Write-Output $output

param(
    [int]$DurationSeconds = 250,
    [int]$IntervalSeconds = 10,
    [string]$OutputFile = "phase19-results/capacity/resources.jsonl"
)

# Aggregate metrics only, from the disposable capacity project.
$ErrorActionPreference = "Stop"
$taskRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
$taskCompose = Join-Path $taskRoot "docker-compose.capacity.yml"
$taskProject = docker compose -f $taskCompose config --format json | ConvertFrom-Json
if ($taskProject.name -ne "xmansx-capacity-check") { throw "Wrong metrics target" }
$taskStarted = Get-Date
while (((Get-Date) - $taskStarted).TotalSeconds -lt $DurationSeconds) {
    $taskIds = @(docker ps --filter "label=com.docker.compose.project=xmansx-capacity-check" --format '{{.ID}}')
    $taskStats = @(docker stats --no-stream --format '{{json .}}' $taskIds |
        ForEach-Object { $_ | ConvertFrom-Json })
    $taskSql = "SELECT count(*), count(*) FILTER (WHERE state='active'), count(*) FILTER (WHERE wait_event_type='Lock') FROM pg_stat_activity WHERE datname='capacity_synthetic' AND usename='capacity_app'"
    $taskPg = docker compose -f $taskCompose exec -T postgres psql -U capacity_owner -d capacity_synthetic -At -c $taskSql
    $taskRedis = @{}
    foreach ($taskService in @("cache", "security", "broker")) {
        $taskRedis[$taskService] = @(docker compose -f $taskCompose exec -T $taskService redis-cli INFO |
            Select-String '^(used_memory:|used_memory_peak:|maxmemory:|connected_clients:|blocked_clients:|evicted_keys:|rejected_connections:)') |
            ForEach-Object { $_.ToString().Trim() }
    }
    @{ time = (Get-Date).ToUniversalTime().ToString("o"); containers = $taskStats;
        postgres_connections_active_lockwaiting = $taskPg; redis = $taskRedis } |
        ConvertTo-Json -Compress -Depth 6 | Add-Content -LiteralPath $OutputFile -Encoding utf8
    Start-Sleep -Seconds $IntervalSeconds
}

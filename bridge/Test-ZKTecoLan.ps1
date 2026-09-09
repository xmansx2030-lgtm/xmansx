param(
    [Parameter(Mandatory = $true)]
    [string]$DeviceIp,
    [ValidateRange(1, 65535)]
    [int]$Port = 4370
)

$parsedIp = $null
if (-not [System.Net.IPAddress]::TryParse($DeviceIp, [ref]$parsedIp)) {
    throw "Invalid device IP address: $DeviceIp"
}

Write-Host "Testing ZKTeco LAN route to $DeviceIp on TCP/$Port..."
$result = Test-NetConnection -ComputerName $DeviceIp -Port $Port -InformationLevel Detailed

[pscustomobject]@{
    DeviceIp      = $DeviceIp
    Port          = $Port
    PingSucceeded = $result.PingSucceeded
    TcpSucceeded  = $result.TcpTestSucceeded
    LocalAddress  = $result.SourceAddress
    Interface     = $result.InterfaceAlias
}

if (-not $result.TcpTestSucceeded) {
    Write-Error "TCP/$Port is not reachable. Check MB2000 Ethernet, subnet, gateway, Comm port, and Windows firewall."
    exit 2
}

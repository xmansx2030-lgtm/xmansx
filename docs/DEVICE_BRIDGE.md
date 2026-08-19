# Device Bridge

`DeviceBridgeInstallation` authenticates a local Bridge with a one-time credential token. The school is derived from that credential; payloads cannot select a school. Credential rotation invalidates the old token.

The Bridge owns LAN access, durable SQLite event queue, retries, batching, heartbeat, Simulator access, roster reads, and roster commands. Browser code never connects directly to a device.

Physical device support is not verified. Simulator verification is the current acceptance gate.

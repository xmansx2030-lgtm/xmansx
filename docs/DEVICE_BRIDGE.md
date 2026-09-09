# Device Bridge

`DeviceBridgeInstallation` authenticates a local Bridge with a one-time credential token. The school is derived from that credential; payloads cannot select a school. Credential rotation invalidates the old token.

The Bridge owns LAN access, durable SQLite event queue, retries, batching, heartbeat, Simulator access, ZKTeco standalone LAN access, roster reads, and roster commands. Browser code never connects directly to a device.

## ZKTeco MB2000 LAN profile

- Device network: static private IPv4 on the same routed school LAN as the Bridge.
- Protocol: TCP (preferred) or UDP; default port `4370`.
- Authentication: numeric Comm Key `0..999999`; it is encrypted at rest in SaaS and is sent only to the authenticated Bridge.
- Time: the device's naive local timestamps are attached to the school's configured IANA timezone before upload.
- Data boundary: attendance events and safe user directory fields only. Face/fingerprint templates are never read, queued, or uploaded.
- Failure behavior: one unreachable device is reported `DEGRADED` and does not stop other devices. Already-read events remain in the durable SQLite queue and are replayed idempotently when Internet access returns.
- Driver: optional `pyzk==0.9` (unofficial, GPL-2.0). Review distribution obligations. The adapter boundary allows a licensed ZKTeco Standalone SDK driver to replace it later.

## Device-side setup

On the MB2000 open **Comm. → Ethernet** and configure IP address, subnet mask,
gateway, and TCP COMM port `4370`. Under **PC Connection**, set the Comm Key
to the same numeric value stored in the manager screen (`0` means blank). Give the
device and Bridge PC reserved DHCP leases or static addresses, and allow outbound
HTTPS from the Bridge. Do not expose port 4370 to the Internet and do not configure
router port forwarding.

## Physical acceptance gate (required before claiming 100%)

1. From the Bridge PC, confirm the device IP is reachable and port 4370 is open.
2. In the manager screen request **اختبار الاتصال**; wait for the next heartbeat and verify `ok`, device time, firmware, serial, and platform.
3. Read the device roster and match one test user to one test student.
4. Record one fingerprint punch and one face punch; confirm one morning-arrival event each, correct school timezone, and no duplicate after the next poll.
5. Disconnect Internet, record a punch, reconnect, and prove the queued event arrives once.
6. Restart the Bridge PC and MB2000 and prove the Windows service resumes automatically.
7. Confirm Arabic display names on this exact firmware before approving roster writes.

Until all seven checks pass on the school's physical serial number and firmware,
the software integration is ready for hardware acceptance but is not certified as
100% device-compatible.

"""Switch only the validated target backup namespace and scheduler flags."""

from pathlib import Path

path = Path("/opt/mowadhabah/application.env")
updates = {
    "BACKUP_ENVIRONMENT": "hetzner-production",
    "BACKUP_SCHEDULE_ENABLED": "true",
    "BACKUP_KEEP_LATEST_ONLY": "true",
    "R2_BACKUPS_PREFIX": "hetzner-production",
}
lines = path.read_text().splitlines()
seen = set()
result = []
for line in lines:
    key = line.split("=", 1)[0]
    if key in updates:
        result.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        result.append(line)
result.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
path.write_text("\n".join(result) + "\n")
path.chmod(0o600)
print("Daily backup enabled in separate Hetzner namespace; original source archive retained.")

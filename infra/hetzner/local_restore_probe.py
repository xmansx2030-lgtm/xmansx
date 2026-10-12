"""Restore the original dump into a new isolated WSL database for comparison."""

import subprocess
import sys
from pathlib import Path

database = "mowadhabah_restore_20261012"
backup = Path(
    "/mnt/c/Users/manso/Documents/PrivateBackups/xmansx/2026-10-12/20261010T180942072380Z_render-production_xmansx.dump"
)
prefix = ["runuser", "-u", "postgres", "--"]
existing = subprocess.run(
    prefix + ["psql", "-qAt", "-c", f"SELECT 1 FROM pg_database WHERE datname='{database}'"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
assert not existing, "Refusing to overwrite an existing restore database"
subprocess.run(prefix + ["createdb", database], check=True)
subprocess.run(
    prefix
    + [
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        database,
        str(backup),
    ],
    check=True,
)
subprocess.run(
    [sys.executable, str(Path(__file__).with_name("sql_inventory.py")), "--database", database],
    check=True,
)

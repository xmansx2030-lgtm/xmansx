"""Set ownership only inside the explicitly isolated synthetic private volume."""

import os
from pathlib import Path


def main():
    if (
        os.environ.get("PARENT_STAGING_LOCAL_ONLY") != "1"
        or os.environ.get("POSTGRES_DB") != "parent_verification"
        or os.environ.get("POSTGRES_HOST") != "postgres"
        or os.getuid() != 0
    ):
        raise RuntimeError("Refusing an unrelated storage environment")
    roots = {
        "GENERATED_DOCUMENTS_ROOT": "private",
        "DATABASE_BACKUP_ROOT": "backups",
        "BACKUP_STORAGE_LOCATION": "repository",
    }
    approved_paths = []
    for setting, name in roots.items():
        root = Path("/var/lib/xmansx-parent-staging") / name
        if (
            os.environ.get(setting) != str(root)
            or root.resolve() != root
            or root.is_symlink()
            or not root.is_dir()
            or not root.is_mount()
        ):
            raise RuntimeError("Synthetic storage requires the exact dedicated mounted volumes")
        paths = [root, *root.rglob("*")]
        if any(path.is_symlink() or not path.resolve().is_relative_to(root) for path in paths):
            raise RuntimeError("Refusing a storage path outside its isolated volume")
        approved_paths.extend(paths)
    # Validate all three mounts and their contents before changing any metadata.
    for path in approved_paths:
        os.chown(path, 65534, 65534, follow_symlinks=False)
        path.chmod(0o700 if path.is_dir() else 0o600)
    print("Synthetic private/backup volumes restricted to the non-root application user")


if __name__ == "__main__":
    main()

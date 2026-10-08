"""Set ownership only inside the explicitly isolated synthetic private volume."""

import os
from pathlib import Path


def main():
    if (
        os.environ.get("PARENT_STAGING_LOCAL_ONLY") != "1"
        or os.environ.get("POSTGRES_DB") != "parent_verification"
        or os.environ.get("POSTGRES_HOST") != "postgres"
    ):
        raise RuntimeError("Refusing an unrelated storage environment")
    for name in ("private", "backups", "repository"):
        root = Path("/tmp/parent-verification") / name
        root.mkdir(parents=True, exist_ok=True)
        if root.resolve() != root or root.is_symlink():
            raise RuntimeError("Synthetic storage volumes must not be symlinks")
        paths = [root, *root.rglob("*")]
        if any(path.is_symlink() or not path.resolve().is_relative_to(root) for path in paths):
            raise RuntimeError("Refusing a storage path outside its isolated volume")
        for path in paths:
            os.chown(path, 65534, 65534, follow_symlinks=False)
            path.chmod(0o700 if path.is_dir() else 0o600)
    print("Synthetic private/backup volumes restricted to the non-root application user")


if __name__ == "__main__":
    main()

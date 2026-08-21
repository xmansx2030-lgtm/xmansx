from collections.abc import Iterable


def retained_backup_ids(
    runs: Iterable,
    *,
    daily: int = 7,
    weekly: int = 4,
    monthly: int = 3,
) -> set[int]:
    ordered = sorted(runs, key=lambda run: run.started_at, reverse=True)
    keep: set[int] = set()

    def retain_distinct(key, limit: int) -> None:
        buckets = set()
        for run in ordered:
            bucket = key(run.started_at)
            if bucket in buckets:
                continue
            if len(buckets) >= limit:
                break
            buckets.add(bucket)
            keep.add(run.id)

    retain_distinct(lambda value: value.date(), daily)
    retain_distinct(lambda value: value.isocalendar()[:2], weekly)
    retain_distinct(lambda value: (value.year, value.month), monthly)
    if ordered:
        keep.add(ordered[0].id)
    return keep

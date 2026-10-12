"""Compute whole-table fingerprints without exporting individual database rows."""

import argparse
import json
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--database", required=True)
parser.add_argument("--container")
options = parser.parse_args()
command = (
    ["docker", "exec", "-i", options.container, "psql", "-U", "postgres"]
    if options.container
    else ["runuser", "-u", "postgres", "--", "psql"]
)
command += ["-qAt", "-d", options.database]


def query(statement):
    result = subprocess.run(
        command,
        input="SET TIME ZONE 'UTC';\n" + statement,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


tables = query(
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
).splitlines()
result = {"tables": {}}
for table in tables:
    identifier = '"' + table.replace('"', '""') + '"'
    statement = (
        "SELECT json_build_object('count', count(*), 'digest', "
        "md5(coalesce(string_agg(row_to_json(t)::text, E'\\n' "
        "ORDER BY (row_to_json(t)::text) COLLATE \"C\"), ''))) "
        f"FROM public.{identifier} t;"
    )
    result["tables"][table] = json.loads(query(statement))
result["invalid_foreign_keys"] = int(
    query("SELECT count(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated;")
)
print(json.dumps(result, sort_keys=True))

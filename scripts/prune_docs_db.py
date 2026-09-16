#!/usr/bin/env python3
"""Remove the modules that left the import closure from the doc-gen4 database.

Usage: prune_docs_db.py DB MANIFEST DOC_DATA_DIR

`doc-gen4 single` replaces the rows of the module it analyzes. Nothing removes
the rows of a module that left the closure, for example after a rename in
Mathlib. `fromDb` resolves links against every module in the database, so a
stale module can attract links to a page that the build does not write.

MANIFEST is the `doc-manifest.json` that `fromDb` writes. It lists one HTML
file per module in the closure, as a path relative to the build directory:
`doc/<Module>/<Path>.html`. This script deletes every module that is not in
that list from the `modules` table. The schema cascades the deletion to the
declaration tables. The script also deletes the marker and trace of each
deleted module in DOC_DATA_DIR, so that a module deleted by mistake is analyzed
again in the next build. The script changes nothing when the manifest names no
module of the database.
"""

import json
import os
import sqlite3
import sys


def module_name(rel_path):
    """Map `doc/Mathlib/Data/Nat.html` to `Mathlib.Data.Nat`, or return None."""
    parts = rel_path.replace(os.sep, "/").split("/")
    if len(parts) < 2 or parts[0] != "doc" or not parts[-1].endswith(".html"):
        return None
    parts = parts[1:]
    parts[-1] = parts[-1][: -len(".html")]
    return ".".join(parts)


def main(argv):
    if len(argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    db_path, manifest_path, doc_data = argv[1:4]

    with open(manifest_path, encoding="utf-8") as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        print("prune: the manifest is not a list of paths; nothing done", file=sys.stderr)
        return 1
    live = {name for name in map(module_name, entries) if name}
    if not live:
        print("prune: the manifest lists no module pages; nothing done", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        names = [row[0] for row in conn.execute("SELECT name FROM modules")]
        # Special pages such as `doc/index.html` also map to names. A manifest
        # that names no module of this database does not describe this build.
        if not live.intersection(names):
            print("prune: the manifest names no module of the database; nothing done", file=sys.stderr)
            return 1
        stale = [name for name in names if name not in live]
        with conn:
            conn.executemany(
                "DELETE FROM modules WHERE name = ?", [(name,) for name in stale]
            )
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()

    for name in stale:
        for suffix in (".doc", ".doc.trace"):
            try:
                os.remove(os.path.join(doc_data, name + suffix))
            except FileNotFoundError:
                pass

    print(f"prune: removed {len(stale)} stale modules, {len(names) - len(stale)} remain")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

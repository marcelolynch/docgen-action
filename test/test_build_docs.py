"""Exercise the build script with cached files and a controlled Lake process."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_docs.sh"


class BuildDocsTest(unittest.TestCase):
    def run_build(self, failures=(), warm=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        build = root / "docbuild/.lake/build"
        if warm:
            for name in (
                "api-docs.db", "doc-data/LibA.doc", "doc-data/LibA.doc.trace",
                "doc-data/LibA.doc.hash", "doc-data/LibA--library.modules",
                "doc-data/references.json", "doc/references.bib",
                "doc-data/LibA--library.docs_built", "doc-data/LibA--library.docs_built.hash",
                "doc-data/LibA--library.docsHeader_built",
                "doc-data/declaration-data-Old.bmp", "doc-data/backrefs-Old.json",
                "doc/Old.html", "doc/Old/Child.html", "doc/navbar.html",
            ):
                file = build / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("cached")
        if warm:
            (root / "site/docs").mkdir(parents=True)
            (root / "site/docs/Old.html").write_text("previous deployment")
        (root / "lean-toolchain").write_text("leanprover/lean4:v4.35.0-rc2\n")
        stub = root / "lake"
        stub.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_ROOT"])
if sys.argv[1] == "update":
    sys.exit(0)
log = root / "calls.jsonl"
calls = log.read_text().splitlines() if log.exists() else []
files = sorted(str(p) for p in pathlib.Path(".lake/build").rglob("*") if p.is_file())
with log.open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "files": files}) + "\\n")
failures = json.loads(os.environ["TEST_FAILURES"])
if len(calls) < len(failures):
    print(failures[len(calls)])
    sys.exit(1)
out = pathlib.Path(".lake/build/doc")
out.mkdir(parents=True, exist_ok=True)
(out / "LibA.html").write_text("current A")
(out / "LibB.html").write_text("current B")
''')
        stub.chmod(0o755)
        # Substitute only the external Lake executable; exercise the actual shell logic.
        script = root / "build_docs.sh"
        script.write_text(SCRIPT.read_text().replace("~/.elan/bin/lake", '"' + str(stub) + '"'))
        (root / "sudo").write_text("#!/bin/sh\nexit 0\n")
        (root / "sudo").chmod(0o755)
        env = dict(os.environ, TEST_ROOT=str(root), TEST_FAILURES=json.dumps(failures),
                   NAME="project", REFERENCES="missing references.bib", HOMEPAGE="site",
                   DOCS_FACETS="LibA:docs LibB:docs", PATH=str(root) + os.pathsep + os.environ["PATH"])
        result = subprocess.run(["bash", str(script)], cwd=root, env=env, capture_output=True, text=True)
        self.assertTrue((root / "calls.jsonl").exists(), result.stdout + result.stderr)
        calls = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
        return root, result, calls

    def test_warm_build_discards_site_and_preserves_analysis(self):
        root, result, calls = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["args"], ["build", "LibA:docs", "LibB:docs"])
        self.assertEqual(calls[0]["files"], sorted(".lake/build/" + p for p in (
            "api-docs.db", "doc-data/LibA.doc", "doc-data/LibA.doc.trace",
            "doc-data/LibA.doc.hash", "doc-data/LibA--library.modules",
            "doc-data/references.json", "doc/references.bib",
        )))
        self.assertEqual((root / "site/docs/LibA.html").read_text(), "current A")
        self.assertTrue((root / "site/docs/LibB.html").exists())
        self.assertFalse((root / "site/docs/Old.html").exists())

    def test_cold_build(self):
        _, result, calls = self.run_build(warm=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(calls[0]["files"], [])

    def test_schema_failure_retries_from_clean_state(self):
        _, result, calls = self.run_build(["Database schema is outdated"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["files"], [])
        self.assertEqual(calls[0]["args"], calls[1]["args"])

    def test_other_failure_stops_without_deployment(self):
        root, result, calls = self.run_build(["unrelated build failure"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertFalse((root / "site/docs/LibA.html").exists())
        self.assertEqual((root / "site/docs/Old.html").read_text(), "previous deployment")

    def test_second_failure_stops_without_deployment(self):
        root, result, calls = self.run_build(["Database schema is outdated", "retry failed"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertFalse((root / "site/docs/LibA.html").exists())
        self.assertEqual((root / "site/docs/Old.html").read_text(), "previous deployment")


if __name__ == "__main__":
    unittest.main()

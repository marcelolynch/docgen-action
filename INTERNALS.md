# Documentation cache

Module analysis is the expensive part of a documentation build. doc-gen4 stores
that analysis in a SQLite database and derives the site from it. The cache
preserves the analysis so that a dependency update only requires work for the
modules whose inputs change.

The site must describe the current build. Before `lake build` runs, the build script
removes generated pages, per-module search data, and HTML completion markers.
It preserves the bibliography copy because the bibliography step can remain
up to date. This also handles files restored by another cache or left in a
reused workspace.

## Required doc-gen4 behavior

This action assumes a doc-gen4 revision with these upstream fixes:

- [#416](https://github.com/leanprover/doc-gen4/pull/416) restricts declaration
  links to modules with pages in the output.
- [#418](https://github.com/leanprover/doc-gen4/pull/418) makes analysis changes
  invalidate the HTML step.
- [#419](https://github.com/leanprover/doc-gen4/pull/419) removes obsolete modules
  from each library before the HTML step.

These fixes must be available in the revision selected for the project's
toolchain. The script normally requests the matching release tag. For nightly
and other toolchains, it requests `nightly-testing` and `main`, respectively.
A toolchain therefore constrains cache reuse, but does not identify an immutable
doc-gen4 revision in every case.

The action leaves database cleanup to doc-gen4. A removed library or dependency
can leave unused rows in the database. The script removes their generated pages and search data before the build. The link filter excludes
their declarations from link resolution. The action does not prune
against `doc-manifest.json`: each HTML invocation describes only its own roots,
so that file cannot identify every live module in a build with several targets.

## Cached state

All paths below are relative to `docbuild/.lake/build`:

- `api-docs.db*` holds the database and any SQLite write-ahead log files.
- `doc-data/*.doc`, `*.doc.trace`, and `*.doc.hash` record completed analysis
  and its inputs. Lake uses them to decide which modules need analysis.
- `doc-data/*--library.modules` records the module lists used for library cleanup.
- `doc-data/references.json*` holds the bibliography data and its Lake trace files.
- `doc/references.bib` is the downloadable bibliography copy.

HTML, per-module search data, and HTML completion markers are derived output.
The cache excludes them. The script also clears them before each build so that
cache restoration and local reuse have the same behavior.

## Cache reuse and recovery

The exact key contains a format version, the hash of `lean-toolchain`, and a hash
of `lake-manifest.json` plus the references file. The toolchain and manifest
paths use `lake-package-directory`; the references path uses the workspace.

On an exact miss, `actions/cache` uses `restore-keys` to find an accessible entry
whose key starts with the supplied prefix. It restores the newest matching
entry. The prefix includes the toolchain hash, so a dependency update can reuse
analysis from the same toolchain. Lake checks the restored analysis traces
against the current inputs.

A successful job saves a new entry when the exact key was absent. An exact hit
keeps its existing entry. Cache format version `v2` separates this file list
from entries that include derived output.

If doc-gen4 reports `Database schema is outdated`, the script discards the
restored build directory and retries once. Other build failures stop the job.
A failure on the retry also stops the job. The upstream schema check must report
incompatibility before it attempts operations that require the new schema.

## Measurements and cache capacity

Measurements on the earlier draft illustrate the cost of analysis and HTML
generation; they do not validate the upstream integration described above.

On Noperthedron, analysis of 2936 dependency modules took 28 minutes, and core
analysis took 13 minutes. HTML generation took about 70 seconds. A dependency
update increased the workflow duration from 17 to 52 minutes without cache
reuse across manifests.

[Playground runs](https://github.com/marcelolynch/LeanDownstreamPlayground/actions?query=branch%3Adocs-cache-experiments)
with about 1100 Mathlib modules produced 3121 pages. The cold documentation step
took 8 minutes and analyzed 609 modules plus core. A dependency update analyzed
one module in 2 minutes 13 seconds. An exact cache hit analyzed none in
2 minutes 11 seconds. HTML generation took about 43 seconds; compilation of
doc-gen4 took about 85 seconds on a warm run. The cache occupied 37 MB, compared
with 51 MB for the HTML cache. A larger Mathlib cache stayed under 130 MB.

Repository caches share a capacity limit. Large `.lake` entries can displace
the documentation cache. Inspect cache usage before disabling other caches:

```sh
gh cache list
gh api repos/<owner>/<repo>/actions/cache/usage
```

Disabling the cache in `leanprover/lean-action` trades storage for build work.
Mathlib can download its own compiled artifacts. Dependencies without an
artifact cache need a source build on each run.

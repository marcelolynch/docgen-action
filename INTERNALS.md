# Internals

This document describes how the action builds the API documentation and what
the GitHub Actions cache holds. It is for maintainers of the action. The README
describes the inputs.

## Pipeline

The action is a composite action. `action.yml` runs these steps in order:

1. `dist/deprecation.js` maps the deprecated input names to environment variables.
2. `dist/index.js` reads `lakefile.toml` and publishes the package name and the
   `docs` facet of each default target.
3. `actions/cache` restores the documentation database. This step runs for
   `push` events when `use-github-cache` and `api-docs` are true.
4. The blueprint step builds the blueprint when `blueprint` is true.
5. `scripts/build_docs.sh` builds the API documentation and copies the HTML to
   `<homepage>/docs`. This step runs for `push` events when `api-docs` is true.
6. Ruby and Jekyll build the homepage when `build-page` is true and the
   homepage folder exists.
7. The action uploads the site and deploys it to GitHub Pages for `push`
   events when `deploy` is true.
8. The post step of `actions/cache` saves the documentation database when the
   job succeeds and the exact key was absent.

## The docs build

`build_docs.sh` creates a Lake package in `docbuild/` in the workspace. Its
`lakefile.toml` requires the project by path and `doc-gen4` at the revision that
matches `lean-toolchain`: the tag `vX.Y.Z` or `vX.Y.Z-rcN` for a release
toolchain, the branch `nightly-testing` for a nightly, and `main` otherwise.
The package shares `.lake/packages` with the project, so Lake clones each
dependency once. The script runs `lake update <project>` and
then one `lake build` with the `docs` facet of each default target.

doc-gen4 builds the documentation in two phases.

The analysis phase. The `docInfo` facet of each module runs `doc-gen4 single`,
which writes the declarations of the module into the SQLite database
`docbuild/.lake/build/api-docs.db`. Lake gates the facet on the marker file
`doc-data/<Module>.doc` and its trace. The trace covers the doc-gen4
executable, the bibliography prepass (which reads the references file), the
core documentation, the `docInfo` marker of each import, and the oleans of the
module. The `coreDocs` target does the same for `Init`, `Std`, `Lake` and
`Lean`, with the markers `doc-data/core-<Name>.doc`. This phase does most of
the work, and its cost grows with the import closure. For example, for a
project that depends on Mathlib and imports about three thousand of its
modules, the analysis of the dependencies takes about 40 minutes on a GitHub
runner.

The HTML phase. The `docs` facet runs `doc-gen4 fromDb` once with the root
modules of the target. `fromDb` computes the transitive import closure from the
database, writes the page of every module in the closure, the search index, the
navigation bar and the static files, and lists the module pages in
`doc-manifest.json`. Lake gates this facet on the marker
`doc-data/<name>.docs_built`. The phase takes about a minute for a closure of
three thousand modules.

The HTML is a function of the database. The database is the expensive state.

## What the cache holds

The cache holds the analysis state:

- `docbuild/.lake/build/api-docs.db*`: the database, and its write-ahead log
  files when they exist.
- `docbuild/.lake/build/doc-data`: the marker files with their traces, and the
  output of the bibliography prepass.

For example, an entry for a project that depends on Mathlib is less than
130 MB compressed.

The cache leaves out the HTML directory `docbuild/.lake/build/doc` for three
reasons. `fromDb` writes it in about a minute. The navigation bar and the
search index include every module page found on disk, so a restored page of a
module outside the closure would appear in both. And the set of files that
doc-gen4 writes belongs to doc-gen4, while the two paths above are stable
across its versions.

## The cache key

The exact key is

    docs-db-v1-<hash of lean-toolchain>-<hash of lake-manifest.json and the references file>

and the fallback prefix is

    docs-db-v1-<hash of lean-toolchain>-

`hashFiles` resolves `lean-toolchain` and `lake-manifest.json` relative to the
Lake package directory, and the references file relative to the workspace.

The toolchain hash comes first because the toolchain selects the doc-gen4
revision, and the database format belongs to that revision. doc-gen4 stores a
hash of its schema in the database and refuses a database with a different
hash. A toolchain change therefore starts a new database.

A change of the manifest, such as a dependency bump, or of the references
file changes the exact key. The fallback prefix restores the most recent database of
the same toolchain, and Lake analyzes only the modules whose trace changed.
`actions/cache` saves the result under the exact key at the end of the job.

The segment `v1` marks the meaning of the cached paths. Change it when the set
of paths or the way the scripts use them changes.

## Invariants that `build_docs.sh` maintains

Three steps in `build_docs.sh` keep the restored state consistent with the
build.

The HTML phase runs on every build. The script deletes the `*.docs_built`
markers and their traces before `lake build`. Lake checks the marker and its
trace, not the HTML files, so a restored marker would skip `fromDb`.

An incompatible database triggers one clean rebuild. When `lake build` fails
and its output contains `Database schema is outdated`, the script deletes
`docbuild/.lake/build` and builds once more. Any other failure stops the
script. The toolchain segment of the key makes this case rare. It remains
possible under the `main` and `nightly-testing` fallbacks, where the doc-gen4
revision can change under a fixed key.

Stale modules leave the database. `single` replaces the rows of the module it
analyzes, and nothing removes the rows of a module that left the closure, for
example after a dependency renames a module. `fromDb` resolves links against every module
in the database, so a stale module can attract links to a page that the build
does not write. After the build, `scripts/prune_docs_db.py` reads the module
pages from `doc-manifest.json`, deletes every other module from the `modules`
table, and deletes their marker files. The schema cascades the deletion to the
declaration tables. The marker deletion means that a module removed by mistake
is analyzed again in the next build. The script changes nothing when the
manifest names no module of the database.

`actions/cache` saves only when the job succeeds, so a failed build does not
persist a partial database.

## The repository cache limit

GitHub keeps at most 10 GB of cache per repository by default and evicts the
least recently used entries beyond that. The documentation database is small
next to that limit. `leanprover/lean-action` caches the whole `.lake`
directory, with the build outputs of every dependency, under a key that
contains the commit hash. For example, for a project that depends on Mathlib,
each entry holds the Mathlib oleans that lean-action downloads with
`lake exe cache get`, each push adds an entry of several gigabytes, and a few
pushes evict the documentation database.

A project that sees a full analysis on every run with an unchanged manifest
should check the cache usage of the repository:

    gh api repos/<owner>/<repo>/actions/cache/usage
    gh api repos/<owner>/<repo>/actions/caches

If the `lake-*` entries fill the limit, `use-github-cache: false` on
lean-action keeps the documentation database alive. The cost of that setting
depends on the dependencies. Lake builds a dependency from source on each run,
except when the dependency has its own cache: for a project that depends on
Mathlib, the Mathlib oleans come from the Mathlib cache, and the cost is that
download plus a rebuild of the project's own modules.

## Limits and directions

The action analyzes the dependencies once per toolchain and per project.
doc-gen4 tracks two changes that would remove that cost: per-package databases
distributed with the cache of a dependency, such as the Mathlib cache (see the
section "Incrementality and
Caching" of leanprover/doc-gen4#347), and interproject linking, which writes
pages for the project's modules only and links to the published documentation
of the dependencies (leanprover/doc-gen4#396). Both reduce the state that this
cache holds. Neither changes what the cache is for.

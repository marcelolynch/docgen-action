# Documentation cache

doc-gen4 builds the documentation in two steps. The analysis step reads every
module of the project and its dependencies into a database. This step is slow:
it takes most of the build time. The HTML step writes the pages and the search
index from the database in about a minute. The action caches the result of the
analysis, so that a build after a dependency update analyzes only the modules
that changed. It runs the HTML step on every build.

## Requirements

The action needs [doc-gen4#416](https://github.com/leanprover/doc-gen4/pull/416)
in the doc-gen4 version that the project uses. A restored database can hold the
rows of modules that are no longer part of the project, for example after a
dependency renames a module. With #416, doc-gen4 links only to pages that the
build writes.

[doc-gen4#419](https://github.com/leanprover/doc-gen4/pull/419) removes those
rows from the database, so that it does not grow with every rename. Before the
action relies on it, #419 must keep the modules that a target names explicitly,
and it must report an old database before it reads the new columns.

## What the cache holds

One cache entry holds the database, the marker file of each analyzed module
with its trace, the module list of each library, and the bibliography data.
`action.yml` lists the exact files. Lake reads a marker to decide whether a
module needs analysis again. The markers and the database must therefore come
from the same build: a marker without its rows in the database makes Lake skip
an analysis that the build needs.

The entry holds nothing that the HTML step writes. Before each build, the
script empties the output directory, deletes the per-module search data, and
deletes the markers of the HTML step, so that the HTML step runs and the site
holds only the pages of this build. The script keeps the copy of the references
file, because Lake skips the step that writes it when the references file is
unchanged.

## Modules that leave the project

A dependency that the project drops can leave its rows in the database. The
search index is written again on every build and does not show them, and #416
keeps the links away from them. The tactics page is the exception: it lists
every tactic in the database and links to its definition directly. A dropped
dependency can therefore leave tactics on that page whose links are broken.
This is open in doc-gen4.

## The cache key

The key has two parts: a hash of the toolchain, then a hash of the manifest
and the references file. A dependency update changes the second part, so no
entry has the exact key. `actions/cache` then restores the newest entry with
the same toolchain part (the `restore-keys` input), and Lake analyzes only the
modules whose inputs changed. At the end of the job, `actions/cache` saves the
result under the new key.

The toolchain part keeps the entries of different doc-gen4 versions apart. The
script uses the doc-gen4 tag that matches the toolchain, and doc-gen4 refuses a
database from a version with a different schema. For the toolchains that use
the `main` or `nightly-testing` branch of doc-gen4, the version can change
under the same toolchain. When doc-gen4 reports `Database schema is outdated`,
the script deletes the build directory and builds once more. Any other failure,
and a failed second build, stop the job.

`actions/cache` saves an entry only when no entry had the exact key, and it
never replaces an entry. Change the version segment `v2` of the key when the
set of cached files or their meaning changes.

## Cache capacity

GitHub keeps at most 10 GB of cache per repository and removes the least
recently used entries beyond that. `leanprover/lean-action` caches the whole
`.lake` directory on every push. For a project that depends on Mathlib, each of
its entries holds the Mathlib build files and takes several GB, so a few pushes
can remove the documentation entry. To see which entries fill the cache:

```sh
gh cache list
gh api repos/<owner>/<repo>/actions/cache/usage
```

`use-github-cache: false` on lean-action keeps the documentation entry. Lake
then builds the project on every push. Mathlib downloads its own build files,
but a dependency without such a download is built from source every time.

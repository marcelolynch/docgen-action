# Documentation cache

Module analysis is expensive; HTML generation is comparatively cheap. The action
caches analysis so that a dependency update can reuse work for unchanged modules.
It generates the pages and search index again to avoid publishing obsolete files.

## Requirements

The action relies on doc-gen4 to validate analysis inputs, resolve links, and
remove obsolete modules. It assumes these upstream fixes are available in the
revision selected for the project:

- [#416](https://github.com/leanprover/doc-gen4/pull/416): declaration lookup uses
  modules with pages in the output.
- [#418](https://github.com/leanprover/doc-gen4/pull/418): analysis changes
  invalidate HTML generation.
- [#419](https://github.com/leanprover/doc-gen4/pull/419): library cleanup removes
  obsolete modules before HTML generation.

Library cleanup must preserve modules explicitly requested for documentation.
Schema validation must report an incompatible database before it attempts
operations that require the new schema. These are prerequisites for integration
with #419.

## What must stay consistent

The database and analysis markers form one cache entry. Lake uses the markers to
check which modules need analysis; a marker without the corresponding database
rows can cause Lake to skip necessary work. Library module lists and bibliography
data belong to the same entry. The exact file patterns are in `action.yml`.

Generated pages and search data must describe the current build. The script
clears those files and their completion markers before HTML generation. It also
replaces the published API directory after a successful build. The bibliography
copy is preserved because Lake can skip its generation when its inputs are unchanged.

Database cleanup belongs to doc-gen4, which knows the modules of each library.
An HTML manifest describes one invocation's roots, so the action cannot use it
to decide which database rows are obsolete across several documentation targets.

A removed dependency can leave unused database rows. Fresh search data excludes
its declarations, and #416 filters declaration lookup. This does not cover every
link: the tactics page reads all stored tactics and constructs definition links
directly. Dropped dependencies can therefore leave stale tactic entries and
broken links. That upstream limitation remains open.

## Reuse and recovery

A dependency update should preserve reusable analysis, while a toolchain change
should start a separate cache. On an exact cache miss, `actions/cache` restores
the newest accessible entry whose key starts with the supplied `restore-keys`
prefix. That prefix includes the toolchain hash. Lake checks the restored
analysis against the current inputs.

The script normally selects the doc-gen4 release tag that matches the toolchain.
Its `main` and `nightly-testing` choices can move, so the toolchain hash alone
does not guarantee database compatibility. When doc-gen4 reports
`Database schema is outdated`, the action discards the build directory and retries
once. Other failures, including a failed retry, stop the build.

An exact cache hit keeps its existing entry. A successful job saves a new entry
when the exact key was absent. Change the cache format version when the required
file set or its interpretation changes.

## Cache capacity

Large caches from other workflow steps can displace the documentation cache.
Inspect the repository's entries and usage before disabling another cache:

```sh
gh cache list
gh api repos/<owner>/<repo>/actions/cache/usage
```

Disabling the cache in `leanprover/lean-action` trades storage for build work.
Mathlib can download its own compiled artifacts. Dependencies without an
artifact cache need a source build on each run.

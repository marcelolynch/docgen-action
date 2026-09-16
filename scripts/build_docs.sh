#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status,
# treat unset variables as an error, and ensure errors in pipelines are not masked.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build HTML documentation for the project
# The output will be located in docs/docs

# Determine the `doc-gen4` revision to use as a dependency,
# based on the `lean-toolchain` of this project:
# either the `v4.X.Y` or `v4.X.Y-rcZ` tags, or the `main` or `nightly-testing` branches.
determine_doc_gen_rev() {
    local toolchain_content
    local toolchain_repository
    local toolchain_revision
    
    # We are going to use the toolchain file to determine the revision,
    # or fall back to the `main` branch.
    if [[ ! -f "lean-toolchain" ]]; then
        echo "Warning: lean-toolchain file not found, falling back to main branch" >&2
        echo "main"
        return 0
    fi
    
    toolchain_content=$(< lean-toolchain)
    
    # Split on repository name and revision.
    toolchain_repository=$(echo "$toolchain_content" | cut -f1 -d:)
    toolchain_revision=$(echo "$toolchain_content" | cut -f2 -d:)
    
    if [[ "$toolchain_repository" != "leanprover/lean4" ]]; then
        echo "Warning: Expected 'leanprover/lean4' as first field in lean-toolchain, got '$toolchain_repository'. Falling back to main branch" >&2
        echo "main"
        return 0
    fi
    
    if [[ "$toolchain_revision" =~ ^v4\.[0-9]+\.[0-9]+(-rc[0-9]+)?$ ]]; then
        echo "$toolchain_revision"
        return 0
    fi
    
    # We match nightly-testing branches by looking for a revision starting with `nightly`.
    if [[ "$toolchain_revision" == *"nightly"* ]]; then
        echo "Warning: Detected nightly build '$toolchain_revision', falling back to nightly-testing branch" >&2
        echo "nightly-testing"
        return 0
    fi
    
    # Default fallback
    echo "Warning: Unexpected toolchain format '$toolchain_revision', falling back to main branch" >&2
    echo "main"
    return 0
}

# Create a temporary docbuild folder
mkdir -p docbuild

# Determine the doc-gen4 revision
DOC_GEN_REV=$(determine_doc_gen_rev)

# Template lakefile.toml
cat << EOF > docbuild/lakefile.toml
name = "docbuild"
reservoir = false
version = "0.1.0"
packagesDir = "../.lake/packages"

[[require]]
name = "$NAME"
path = "../"

[[require]]
scope = "leanprover"
name = "doc-gen4"
rev = "$DOC_GEN_REV"
EOF

# Initialise docbuild as a Lean project
cd docbuild

# Place references.bib in the location expected by doc-gen4
if [ -f ../$REFERENCES ]; then
  mkdir -p docs
  cp ../$REFERENCES ./docs/references.bib
fi

# Disable an error message due to a non-blocking bug. See Zulip
MATHLIB_NO_CACHE_ON_UPDATE=1 ~/.elan/bin/lake update "$NAME"

# The `docs` facet writes the HTML in one `fromDb` pass and records the marker
# `doc-data/<target>.docs_built`. Lake checks the marker and its trace, not the
# HTML files. The cache restores the marker, so this deletion makes the HTML
# pass run on every build. See INTERNALS.md.
rm -f .lake/build/doc-data/*.docs_built .lake/build/doc-data/*.docs_built.trace

read -r -a docs_facets <<< "$DOCS_FACETS"

# Build the docs. doc-gen4 refuses a database written by a version with a
# different schema. A restored database can hit this when the doc-gen4 revision
# changes under an unchanged toolchain. In that case, build once more from a
# clean build directory. Any other failure stops the script.
build_log=$(mktemp)
if ! ~/.elan/bin/lake build "${docs_facets[@]}" 2>&1 | tee "$build_log"; then
  if grep -q "Database schema is outdated" "$build_log"; then
    echo "::warning::The cached documentation database does not match this doc-gen4 version. Rebuilding the documentation from a clean state."
    rm -rf .lake/build
    ~/.elan/bin/lake build "${docs_facets[@]}"
  else
    exit 1
  fi
fi

# Remove the modules that left the import closure from the database, so that
# the next build links only to pages that it writes.
python3 "$SCRIPT_DIR/prune_docs_db.py" .lake/build/api-docs.db .lake/build/doc-manifest.json .lake/build/doc-data \
  || echo "::warning::Could not prune stale modules from the documentation database."

# Copy documentation to `$HOMEPAGE/docs`
cd ../
mkdir -p "$HOMEPAGE"
sudo chown -R runner "$HOMEPAGE"
cp -r docbuild/.lake/build/doc "$HOMEPAGE/docs"

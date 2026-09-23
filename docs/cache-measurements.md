# Documentation cache measurements

Measurements on the earlier draft illustrate the cost of analysis and HTML
generation. They do not validate the [upstream integration](../INTERNALS.md#requirements).

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

The Playground runs used toolchain v4.35.0-rc1 with the lean-action cache disabled.

- [Cold build](https://github.com/marcelolynch/LeanDownstreamPlayground/actions/runs/35166780870)
- [Dependency update](https://github.com/marcelolynch/LeanDownstreamPlayground/actions/runs/35167935536)
- [Exact cache hit](https://github.com/marcelolynch/LeanDownstreamPlayground/actions/runs/35168244444)

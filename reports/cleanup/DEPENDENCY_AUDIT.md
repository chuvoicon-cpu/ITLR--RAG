# Dependency audit · 2026-11-19

Python requirements use version ranges. The requirements-based pip audit reported
zero known vulnerabilities across 117 resolved packages. An independent audit of the
installed environment reported zero known vulnerabilities across 118 packages.
`pip check` reported no conflicts. Package installation previously lacked Prometheus
and OpenTelemetry declarations. The four dependencies already installed through
`requirements.txt` are now declared for direct package installation too.
The duplicate `httpx` line was removed and a manifest parity regression covers both paths.

npm dev and runtime audits returned **0** for the same lockfile. `picomatch@4.0.7` remains
a development transitive dependency through the Vitest/Vite toolchain. The registry
previously returned 12 chained High findings. The advisory was withdrawn on 2026-11-18
and the releases page still lists 4.0.7. Keep the normal High CI gate and review the
registry if it reports the advisory again. The npm lockfile was preserved.
[GitHub advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) · [Upstream releases](https://github.com/micromatch/picomatch/releases)

The repository-wide license remains unverified. Source attribution stays with
[curated data](../../data/README.md). A full software bill of materials, transitive license
review, and production image vulnerability certification remain open.

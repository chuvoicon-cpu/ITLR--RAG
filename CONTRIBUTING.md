# Contributing

Use [the developer guide](docs/development/README.md) to set up and verify changes.
Follow [AGENTS.md](AGENTS.md) and the repository's [quality constraints](CONSTRAINTS.md).

- Explain the behavior affected and the tests used to verify it.
- Capture a failing regression before fixing a bug. Run the focused tests and the full
  suites before handing off a release candidate.
- Keep test fixtures and historical measurements traceable. Changing the curated corpus
  requires provenance and license review. Changes to frozen judgments need a separate
  versioned evaluation with a documented reason.
- Document configuration, API, and operational changes. Add an ADR when a decision changes
  a persistent contract or architectural boundary.
- Use disposable databases and artifact folders for experiments. Keep real secrets and
  unredacted logs outside Git. Report security concerns privately. [Security policy](SECURITY.md)

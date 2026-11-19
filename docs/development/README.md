# Developer guide

Python 3.11+ and Node.js 22 match the supported development tooling. Use an isolated
virtual environment and install Web packages from the lockfile.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
(cd web && npm ci)
```

For Python packaging, `pip install '.[dev,eval]'` is the alternative installation path.
The pytest configuration guards parity between the dependency manifests. Model weights
require their own cache and the Web app requires PostgreSQL. [Local setup](../../deploy/DEPLOY.md)

Run the commands in [Testing](../TESTING.md) and the repository's [contribution guide](../../CONTRIBUTING.md).
The hosted CI uses disposable services and fixture credentials. For model benchmarks,
capture the real provider workload and code/artifact identity outside the unit suite.

The cleanup removes the Makefile target that deleted artifacts and reports recursively.
Keep manual retention outside tracked paths and verify that workers and backups are
accounted for before removing any generated artifact.

# Deletion manifest · 2026-11-19

| Path | Reason and dependency evidence | Risk | Rollback | Verification |
|---|---|---|---|---|
| `web/nodemon.json` | Tracked legacy watcher config. `web/package.json` uses `tsx watch src/server.ts` for development, `tsc` for build and Node for runtime. No Nodemon dependency, workflow, docs command, or tracked/untracked source reference. | A maintainer manually using a globally installed Nodemon loses the implicit settings. The supported `npm run dev` entry point is unchanged. | Recover the unchanged baseline file with `git show ce53b14:web/nodemon.json` or use `npm run dev`. | Web typecheck, lint, build, tests, and isolated Compose smoke. |

The removed Make target was verified with `make -n clean`. The baseline dry run printed
a recursive deletion of artifacts and reports. The final Makefile has no such target.
No user data, existing local database, artifact, report, test, or local cache was removed. Duplicate logs and empty
historical files keep their original paths for checksums and provenance.

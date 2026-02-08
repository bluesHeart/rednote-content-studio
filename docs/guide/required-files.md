# Required Files Matrix

This document clarifies which files are required for runtime, development, and repository governance.

## Runtime Required (Core)

- `app.py` (Web entrypoint)
- `requirements.txt` (dependencies)
- `scripts/` (CLI and conversion pipeline)
- `web/` (API + frontend static assets)

## Runtime Optional (Helpful)

- `examples/` (sample input only)
- `docs/showcase/` (showcase articles and images)
- `output/README.md` and `output/.gitkeep` (directory hygiene only)

## Repo/Governance Required (Open Source)

- `README.md` (entry)
- `README.zh-CN.md` and `README.en.md` (bilingual docs)
- `LICENSE` (MIT)
- `.gitignore`

## Removed Optional Artifacts

- `SKILL.md` and its moved copy were removed from this repository.

Reason: they are not runtime dependencies and would only add repository noise.

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

## AI-Assistant Specific (Not Runtime Required)

- `docs/guide/ai-assistant-skill.md` (formerly `SKILL.md`)

This file is only used when an AI coding assistant reads local skill instructions.
It is not imported by application code, and deleting it will not affect runtime behavior.


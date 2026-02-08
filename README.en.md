# rednote-content-studio

Turn Markdown into publish-ready REDnote cards, while keeping the final-mile editing control in your hands.

> GitHub: https://github.com/bluesHeart/rednote-content-studio
>
> If this project helps you, please give it a **Star** ⭐

---

## What You Get

- **Controllable generation**: block-level edit, lock, and partial rewrite
- **Text-image alignment**: images flow with content, no random stacking
- **Dual entry points**: CLI batch mode + Web UI
- **Production artifacts**: `txt/html/png/json`

---

## Preview

![Demo Cards A](docs/showcase/article_assets/21_cards_pair_clean_a.png)

![Demo Cards B](docs/showcase/article_assets/22_cards_pair_clean_b.png)

Case study (with screenshots): `docs/showcase/cases/rednote_final_mile_story.md`

---

## Quick Start

### 1) Install

```bash
pip install -r requirements.txt
```

### 2) Configure model access

At least one key is required:

- `SKILL_LLM_API_KEY` (or `OPENAI_API_KEY`)

Optional:

- `SKILL_LLM_BASE_URL` (default: `https://api.openai.com/v1`)
- `SKILL_LLM_MODEL` (default: `gpt-4o-mini`)

### 3) Run

CLI:

```bash
python scripts/main.py examples/test_input.md --output ./output
```

Web:

```bash
python app.py --port 8000
```

Open: `http://127.0.0.1:8000`

---

## Required vs Optional Files

See: `docs/guide/required-files.md`

In short: `SKILL.md` is **not required** for runtime and has been removed from this repository.

---

## Open Source

- License: `MIT` (see `LICENSE`)
- Repository visibility: Public

---

## Contributing

- Issues: https://github.com/bluesHeart/rednote-content-studio/issues
- PRs are welcome

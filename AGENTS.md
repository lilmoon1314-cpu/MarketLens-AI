# Repository Guidelines

## Project Structure & Module Organization

MarketLens AI is a Chinese-first product feedback analysis project. `MarketLens_AI_PRD_v0.1.md` contains the v0.2 PRD; its original filename is retained. The local analysis workflow, persistence, and Chinese Dashboard are implemented through F12. Taobao collection remains planned.

Python modules live under `src/marketlens/`, automated tests under `tests/`, and design/progress documents under `docs/`. Keep future collection, NLP filtering, orchestration, and visualization separate. Use sanitized fixtures under `tests/fixtures/`; runtime data and browser sessions belong in ignored `.local/`.

## Build, Test, and Development Commands

Use Python 3.12 and uv from the repository root:

- `uv sync --locked --group dev`: install the locked development environment.
- `uv run --locked pytest -q`: run offline tests.
- `uv run --locked ruff check .`: lint Python sources.
- `uv run --locked ruff format --check .`: verify formatting.
- `uv build --no-sources`: build wheel and source distribution.

Install optional `workflow`, `llm`, `nlp`, `ui`, or `collector` extras only as needed. Use the `workflow` extra for graph integration tests and the `marketlens analyze --demo` CLI. Run the Dashboard with `uv run --extra workflow --extra llm --extra ui streamlit run src/marketlens/ui/app.py`; real mode also needs `nlp`.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions/modules, and `PascalCase` classes. Add type hints to public interfaces. Ruff enforces formatting and selected lint rules with a 100-character line length. Keep agent schemas explicit and insights linked to evidence.

Maintain types in `src/marketlens/contracts/`; regenerate `docs/schemas/` with `uv run --locked python -m marketlens.contracts.export` after contract changes. Do not hand-edit generated schemas.

## Testing Guidelines

Use pytest and `test_*.py` filenames. Cover affected contracts, routing, evidence, and failure behavior. Mock external services; `model_smoke` and `live_api` tests are excluded by default and require explicit selection. No coverage threshold is established.

Treat PRD accuracy and performance targets as evaluation goals, not established results. Record datasets and measurement methods.

For frontend layout or visual acceptance, save screenshots in `test/pic_test/`. Create it when needed, use descriptive filenames such as `dashboard-desktop-1440x900.png`, and link screenshots in the final response.

## Commit & Pull Request Guidelines

Implement one feature per iteration. Update `docs/PROGRESS.md`, run necessary checks, then commit and push to the authorized remote. Use imperative subjects such as `feat(F00): bootstrap development environment`. PRs describe behavior, relevant requirements, validation, and visual evidence. Never force-push or include unrelated changes.

## Security & Configuration

Keep API credentials outside committed files. Use sanitized review fixtures and avoid logging credentials or unnecessary personal data. Document required environment variables when integrations are added.

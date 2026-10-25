## Project memory (read first)
This repository uses the `ratifact` MCP server with project `anistream-scaffold`. Before working, call
`get_context("anistream-scaffold")`. Only **accepted** decisions are rules; proposals are not implemented without the
user's confirmation. Code tasks run with `/run-task T-NNN` (in Codex: `$run-task T-NNN`).
Decisions, pending items and tasks live in `ratifact`; on a contradiction with another memory, the
accepted decision wins.
Test command (from the repository root): `cd scraper && .venv/bin/python -m pytest tests -q && cd ../anistream && pnpm test && pnpm type-check`

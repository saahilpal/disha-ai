# Synapse AI Agent Directives

This project uses Synapse for persistent structural context, graph navigation, and memory.
Follow these operational guidelines:

## 1. Session Start & Context Loading
- At the start of any conversation or task, call the MCP tool `get_session_preamble()`.
- Review the active branch, latest checkpoint, and approved negative constraints (lessons).
- If resuming an existing task, call `restore_checkpoint()`.
- Never repeat failures listed in approved lessons.

## 2. Progressive Code Navigation & Search
- When exploring, call `search(query="...", summary_only=True)` first to find relevant symbols with minimal token overhead.
- Use `get_skeleton(file_path="...")` to inspect function signatures, docstrings, and classes without implementation bodies (85% token savings).
- Use `get_outline(file_path="...")` to inspect file structure and line ranges.
- Use `read_symbol(symbol="...", file_path="...")` to read exact symbol code without reading entire files.
- Before modifying a symbol, use `get_callers(symbol="...")` or `get_neighborhood(symbol="...", direction="upstream")` to check caller blast radius.

## 3. Verification & Testing
- Use `get_diff()` to review uncommitted code changes.
- Use `get_test_recommendations()` to identify impacted test files and receive recommended pytest commands.

## 4. Session Checkpointing & Memory
- Before ending a complex task or when context is high, call `create_checkpoint(doing="...", next_step="...")`.
- Log key architectural decisions using `log_decision(content="...", context_info="...")`.
- Save critical environment facts or non-code observations using `remember(key="...", content="...")`, and look up with `recall(key="...")`.

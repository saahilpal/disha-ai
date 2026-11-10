# Verified Agent Capabilities

**Checked:** 2026-11-09
**Rule:** This file records observed tools only. Older machine, model, test, deployment, and score claims were not carried forward because they were not re-verified.

## Host and repository

| Capability | Observed state |
|---|---|
| Host architecture | macOS, `arm64`; exact hardware model not verified in this session |
| Current branch | `main` |
| Working tree | 33 uncommitted files before this priority interrupt; preserve them |
| Frontend source | `disha_core/frontend/index.html`, `app.js`, `style.css`; plain JavaScript, no Vite/TypeScript/framework in package manifests |
| Root package | npm scripts for sync, diagnostics, UX script, Vercel packaging, and duplication scan; no declared frontend framework |
| Runtime versions | Node v26.0.0, npm 11.12.1, Python 3.15.0, Docker 29.6.2, cloudflared 2026.9.3 |
| Chrome | `/Applications/Google Chrome.app` exists |
| Playwright | Node package resolves as `playwright@1.65.0`, marked extraneous by npm; browser launch still needs verification |
| Axe | `axe-core` does not resolve from the root package |
| Framework packages | `vite`, `svelte`, and `react` do not resolve from the root package |
| Docker services | Existing backend, Postgres, and proxy containers are running; database is persistent and must not receive destructive or synthetic test mutations |
| External install policy | No global installs. Any new project dependency must be pinned, justified, and documented. |

## Structural navigation and memory

- Synap CLI exists at `/Users/nitrousoxide/.local/bin/synap`.
- `synap status`: daemon stopped; local index reports 357 files and 1,103 symbols; zero approved lessons; no checkpoint on `main`.
- `synap search` returned structural results, but its local LLM path failed with “Operation not permitted”; structural-only results were available.
- `synap context` failed while reading the dirty diff (`git diff-tree` error followed by SQLite “unrecognized token: #”). No checkpoint or lessons were found by their read-only commands.
- No Synapse MCP tools are connected in this session. The CLI is the available fallback; do not claim MCP navigation/checkpoint calls succeeded.

## MCP and documentation tools

- Connected tools include web search, Codex thread/worktree management, and document/app utilities.
- Context7 MCP and Chrome DevTools MCP are not connected.
- Official web documentation can be checked through the connected web search tool.
- No direct browser automation MCP is connected. Use installed Chrome and the existing Playwright package only after verifying it launches.
- `modern-web-guidance` local skill requests `npx` network retrieval; it has not been run because the sandbox requires explicit network approval.

## Relevant local skills inspected

- `~/.gemini/config/skills/ui-styling/SKILL.md`
- `~/.gemini/config/skills/design-system/SKILL.md`
- `~/.gemini/config/plugins/modern-web-guidance-plugin/skills/modern-web-guidance/SKILL.md`
- `~/.agents/skills/browser-qa/SKILL.md`
- `~/.agents/skills/e2e-testing/SKILL.md`
- `~/.agents/skills/tdd-workflow/SKILL.md`

No matching local skill named `frontend-design` or `webapp-testing` was found in the searched roots. The selected skills emphasize truthful browser evidence, responsive/accessibility checks, network approval for the modern guidance CLI, and tests before implementation. Do not add unrequested UI kits.

## Verification still required

- Confirm Chrome/Playwright can open the running local app and save baseline screenshots.
- Inspect every required viewport and state, including 320px, 1920px, dark mode, keyboard, offline, errors, and live-call lifecycle.
- Verify the current app stack and dependencies before choosing a replacement frontend.
- Do not report live Cloudflare, model, or database mutation tests from container status alone.

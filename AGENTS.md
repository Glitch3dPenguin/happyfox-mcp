# AGENTS.md

This repository contains a single-file Python MCP (Model Context Protocol) server that
connects AI agents to the HappyFox Help Desk API (v1.1). All server logic lives in
`happyfox_mcp.py` — there is no package structure, test suite, or lint config.

The server exposes 16 tools: 9 read (`list_tickets`, `get_ticket_details`,
`get_ticket_messages`, `get_ticket_attachments`, `download_attachment`, `list_statuses`,
`list_categories`, `list_priorities`, `list_staff`) and 7 write (`add_ticket_update`,
`create_ticket`, `suggest_ticket_rename`, `change_ticket_status`, `assign_ticket`,
`change_ticket_priority`, `change_ticket_category`).

## Setup commands

- Install deps: `pip install -r requirements.txt` (needs Python 3.10+; the Docker image uses 3.12)
- Credentials come from environment variables — copy from `.env.example` / README:
  - `HAPPYFOX_DOMAIN` (e.g. `acme.happyfox.com`, `acme.happyfox.net` for EU)
  - `HAPPYFOX_API_KEY`
  - `HAPPYFOX_AUTH_CODE`
  - Optional: `MCP_TRANSPORT` (`stdio` default | `streamable-http` | `sse`), `PORT` (default `8000`)
- There is no build step and no virtualenv/lockfile in the repo.

## Running the server

- Local: `HAPPYFOX_DOMAIN=... HAPPYFOX_API_KEY=... HAPPYFOX_AUTH_CODE=... python happyfox_mcp.py`
  (defaults to `stdio`, which is how AI clients launch it)
- HTTP transports bind `0.0.0.0`; stdio binds `127.0.0.1`.
- Endpoints: Streamable HTTP is served at the **root** path `/` (not FastMCP's default
  `/mcp`) and SSE at `/sse`. `streamable_http_path` and `sse_path` are set in the
  `FastMCP(...)` constructor — do not "fix" them back to defaults.
- `host`/`port` are passed to the `FastMCP(...)` constructor, NOT to `.run()` — that is
  the SDK API contract; don't move them.
- Container: `docker compose up -d` (image `ghcr.io/glitch3dpenguin/happyfox-mcp`,
  `MCP_TRANSPORT=streamable-http` is the container default via the Dockerfile).

## Verifying changes

There is **no test suite and no linter** in this repo. Verify by:

1. `python3 -m py_compile happyfox_mcp.py` — must pass.
2. Importing the module with the `mcp` SDK (Python 3.10+) and enumerating tools, e.g.:
   ```bash
   HAPPYFOX_DOMAIN=x HAPPYFOX_API_KEY=x HAPPYFOX_AUTH_CODE=x MCP_TRANSPORT=stdio \
     python -c "import asyncio, happyfox_mcp as m; print([t.name for t in asyncio.run(m.mcp.list_tools())])"
   ```
   All 16 tool names should be listed.
3. For behavior checks without real credentials, stub `requests` (and optionally
   `mcp.server.fastmcp`) in `sys.modules` before importing the module, then call the
   tool functions directly with fixture ticket payloads.
4. The only CI is `.github/workflows/docker-publish.yml` (image build/publish on push
   to `main` and on release) — it does not run any tests, so a broken module is only
   caught by the build step. Be strict about local verification.

## Code style and architecture

- **Single file by design.** Keep all tools in `happyfox_mcp.py`; don't split into a
  package unless explicitly asked.
- **Every HappyFox HTTP call must pass `timeout=30`** (GET and POST). This was a
  deliberate fix — tool calls without timeouts can hang an agent forever.
- **Context-window safety is the core design goal.** Read tools return compact,
  human/agent-readable formatted strings, never raw JSON dumps. `list_tickets` must
  never include message bodies; details come from the per-ticket tools on demand.
  Use `_truncate()` for long text (default 300 chars; 600 for the opening message in
  `get_ticket_details`).
- Auth is HTTP Basic: `_auth()` returns `(API_KEY, AUTH_CODE)`. `BASE_URL` is
  `https://{HAPPYFOX_DOMAIN}/api/1.1/json`.
- Attachment collection lives in `_collect_attachments()`: it merges
  `first_message.attachments`, top-level `attachments`, `updates[].message.attachments`,
  and `updates[].attachments`, deduping by `id` and tagging each with `_source`.
  `get_ticket_attachments` additionally falls back to scanning the `first_message`
  HTML for inline `cid:` references and resolving them via
  `GET /attachment_by_cid/{cid}` — keep that fallback defensive (only accept a 200
  response; it is a safe no-op on accounts where the endpoint doesn't exist).
- `download_attachment(ticket_id, attachment_id)` re-fetches the ticket to locate the
  attachment, then downloads with auth first and **retries without auth** (HappyFox
  serves pre-signed S3 URLs that must not receive a Basic-auth header). Image types
  (png/jpg/jpeg/gif/webp, by MIME or extension) are returned as a native
  `mcp.server.fastmcp.Image` so agents can view them inline; `jpeg` is normalized to
  `jpg`. Don't replace this with writing files to the server's local disk — remote
  MCP clients can't read the server's filesystem.
- Log noise suppression at the top of the module (`mcp.server.streamable_http` → INFO,
  `starlette.requests` → WARNING) is intentional; it keeps HTTP-transport logs clean.
- Write tools generally require a `staff_id` (the actor) and post **immediately with
  no undo** — keep the "confirm with the user first" instruction in every write tool's
  docstring.

## HappyFox API gotchas (learned the hard way — do not regress)

- Ticket endpoints are **singular**: `/ticket/{id}/`, `/ticket/{id}/staff_update/`,
  `/ticket/{id}/staff_pvtnote/`. The plural `/tickets/{id}/` is wrong (only the
  collection endpoint `/tickets/` is plural).
- Private notes go to `staff_pvtnote` (not `staff_private_note`) with `{"staff": id, "plaintext": ...}`.
- Public replies go to `staff_update` with `plaintext`; set `update_customer` to email
  the contact; `status`, `assigned_to`, `priority`, and `category` can be changed in
  the same `staff_update` call.
- `create_ticket` payload uses `text` (not `message`), plus `subject`, `name`,
  `email`, `category`, optional `priority`/`assignee`.
- **The v1.1 API cannot rename a ticket subject.** `suggest_ticket_rename` is a
  workaround that posts a private note with the suggested title for a human to apply
  in the UI. Don't attempt a "real" rename endpoint — it doesn't exist.
- `list_tickets` accepts `status` as `_pending` (default), `_all`, `_completed`, or a
  numeric status ID; `size` is clamped to 50; pagination info comes from `page_info`.
- Attachment metadata can be absent even when `attachments_count > 0` (inline CID
  references in HTML) — that's why the CID fallback exists.
- EU accounts use the `happyfox.net` domain instead of `happyfox.com`.

## Tool guidance (for agents consuming this server)

Recommended workflow:

```
1. list_tickets()                          # Triage the queue — titles only
2. get_ticket_details(ticket_id)           # Metadata + opening message
3. get_ticket_messages(ticket_id)          # Full thread when ready to reply
4. get_ticket_attachments(ticket_id)       # List files, if any are attached
5. download_attachment(ticket_id, id)      # View an attached image inline
6. [show draft reply to user for approval]
7. add_ticket_update(ticket_id, ...)       # Post approved reply
```

- **Always** confirm drafted replies/notes with the user before calling a write tool;
  posts are immediate and cannot be unsent.
- Resolve IDs with the `list_*` tools before acting — never hardcode
  staff/status/priority/category IDs; they differ per account.
- Use `list_statuses()` before `change_ticket_status()`, `list_priorities()` before
  `change_ticket_priority()`, `list_categories()` before category filters/changes, and
  `list_staff()` for any write tool that takes `staff_id`.

## Deployment

- The Docker image is built on every push to `main` and on every published release,
  and pushed to `ghcr.io/glitch3dpenguin/happyfox-mcp` with tags `:latest`,
  `:sha-<commit>`, and semver tags (`:v2.1.0`, `:v2.1`, `:v2`) for tagged releases.
- The container serves Streamable HTTP at `http://<host>:8000/` and SSE at
  `http://<host>:8000/sse`.
- After user-facing changes, update the README (tool tables, endpoint docs, and the
  Changelog) in the same commit.

## Commit and PR guidelines

- Commit messages: imperative, concise, one subject line (repo style:
  "Add ticket priority/assignment/category tools", "Fix: ..."). A short body is fine
  for non-obvious changes.
- Don't commit secrets; credentials only via environment variables.
- Pushes to `main` trigger the Docker build/publish — make sure the module at least
  compiles before pushing.
- Release flow: create a semver tag (e.g. `v2.1.0`) and a GitHub release; CI tags the
  image automatically.

## Security

- Never log or echo `HAPPYFOX_API_KEY` / `HAPPYFOX_AUTH_CODE`; the code must never
  include real credentials or real customer data (fixtures in stub-based checks must
  use fake values).
- Write tools have real side effects on a live help desk — treat them as
  production-affecting and keep the confirm-before-post contract in docstrings.

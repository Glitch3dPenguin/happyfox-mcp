# HappyFox MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI agents to the HappyFox Help Desk API. Designed to be **context-window safe** — ticket lists return titles and metadata only, so agents can triage a full queue without blowing out their context. Full message bodies are fetched on demand, one ticket at a time.

Supports **stdio** (local), **Streamable HTTP**, and **SSE** transports.

---

## Features

- **Context-safe ticket listing** — compact summary table (ID, status, priority, assignee, subject). No message bodies in list output.
- **On-demand detail fetching** — pull metadata or the full message thread for a single ticket when you need it.
- **Attachment viewing & downloading** — images are returned natively so the agent can see them inline; other files return metadata + URL.
- **Status management** — change ticket status, close tickets, look up all available statuses by ID.
- **Priority & assignment** — escalate/de-escalate priority and assign or reassign tickets to staff.
- **Category management** — move tickets between categories, filter the queue by category.
- **Draft → confirm pattern** — write tools are designed to be confirmed by the user before posting.
- **Title rename suggestions** — the v1.1 API can't rename subjects, so the agent posts a private note with a suggested title for a human to apply in the UI.
- **Private notes** — post internal staff notes that are never sent to the contact.
- **Full ID lookup** — resolve staff, status, priority, and category IDs before acting, no hardcoding values that differ between accounts.

---

## Tools

### Read Tools

| Tool | Description |
|---|---|
| `list_tickets` | Compact table of tickets — titles and metadata only. Supports filtering by status, search query, category, and pagination. |
| `get_ticket_details` | Structured metadata + truncated opening message for one ticket. |
| `get_ticket_messages` | Full conversation thread for one ticket. Returns the most recent N messages (default 5). |
| `get_ticket_attachments(ticket_id)` | List all attachments on a ticket (opening message + every reply) with IDs, types, sizes, and which message each came from. |
| `download_attachment(ticket_id, attachment_id)` | Fetch one attachment. Images (PNG/JPG/GIF/WEBP) are returned natively so the agent can view them; other file types return metadata + URL. |
| `list_statuses` | All statuses in your HappyFox account with their IDs. |
| `list_categories` | All ticket categories with their IDs (for `list_tickets` filtering and `change_ticket_category`). |
| `list_priorities` | All ticket priorities with their IDs (for `change_ticket_priority`). |
| `list_staff` | All staff/agents with their IDs. |

### Write Tools

| Tool | Description |
|---|---|
| `add_ticket_update` | Post a public reply or private internal note to a ticket. Optionally change status in the same call. |
| `create_ticket` | Open a new support ticket. |
| `suggest_ticket_rename(ticket_id, suggested_subject, staff_id)` | Post a private note suggesting a better title (the v1.1 API cannot rename subjects — an agent applies it in the UI). |
| `change_ticket_status` | Change ticket status only (e.g. close, put on hold). |
| `assign_ticket` | Assign or reassign a ticket to a staff member. |
| `change_ticket_priority` | Change ticket priority (e.g. escalate to Urgent). |
| `change_ticket_category` | Move a ticket into a different category. |

---

## Deployment

### Option 1 — Container (Recommended)

Running as a container means every client always uses the latest version.
The image is built automatically on every push to `main` via GitHub Actions
and published to GitHub Container Registry.

#### docker-compose / Portainer

```yaml
services:
  happyfox-mcp:
    image: ghcr.io/glitch3dpenguin/happyfox-mcp:latest
    container_name: happyfox-mcp
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      HAPPYFOX_DOMAIN: "yourcompany.happyfox.com"
      HAPPYFOX_API_KEY: "your_api_key_here"
      HAPPYFOX_AUTH_CODE: "your_auth_code_here"
      MCP_TRANSPORT: "streamable-http"
      PORT: "8000"
```

```bash
docker compose up -d
```

The MCP endpoint will be available at the **root** path (the server is configured to serve at `/`, not FastMCP's default `/mcp`):
```
http://<host>:8000/
```

With `MCP_TRANSPORT=sse` the endpoint is `http://<host>:8000/sse`.

#### Portainer via Stack

1. In Portainer, go to **Stacks → Add stack**
2. Paste the `docker-compose.yml` contents above
3. Fill in your HappyFox credentials in the environment section
4. Deploy

#### Connecting your AI client to the container

| Field | Value |
|---|---|
| **Transport** | Streamable HTTP |
| **URL** | `http://<your-server-ip>:8000/` |

In `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "happyfox": {
      "type": "http",
      "url": "http://<your-server-ip>:8000/"
    }
  }
}
```

> **Tip:** If you're running behind a reverse proxy (Nginx, Caddy, Traefik), you can expose this on a subdomain with TLS instead of a raw port.

---

### Option 2 — Local (stdio)

Run the server as a local process on the same machine as your AI client.
No container required, but each machine needs its own install.

#### Install

```bash
git clone https://github.com/Glitch3dPenguin/happyfox-mcp.git
cd happyfox-mcp
pip install -r requirements.txt
```

#### AI client configuration

In `claude_desktop_config.json` (or equivalent):
```json
{
  "mcpServers": {
    "happyfox": {
      "command": "python3",
      "args": ["/absolute/path/to/happyfox_mcp.py"],
      "env": {
        "HAPPYFOX_DOMAIN": "yourcompany.happyfox.com",
        "HAPPYFOX_API_KEY": "your_api_key_here",
        "HAPPYFOX_AUTH_CODE": "your_auth_code_here"
      }
    }
  }
}
```

> **⚠️ The path in `args` must be absolute.** AI clients cannot resolve relative paths.
>
> - Windows: `["C:\\Users\\Name\\happyfox-mcp\\happyfox_mcp.py"]`
> - Mac/Linux: `["/home/username/happyfox-mcp/happyfox_mcp.py"]`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `HAPPYFOX_DOMAIN` | ✅ | Your HappyFox subdomain, e.g. `yourcompany.happyfox.com` |
| `HAPPYFOX_API_KEY` | ✅ | API key from HappyFox account settings |
| `HAPPYFOX_AUTH_CODE` | ✅ | Auth code from HappyFox account settings |
| `MCP_TRANSPORT` | — | `streamable-http`, `sse`, or `stdio` (default: `stdio`) |
| `PORT` | — | Port to bind on for HTTP transports (default: `8000`) |

> **EU accounts:** Use `yourcompany.happyfox.net` instead of `.com`.

See [Generating API Keys](https://support.happyfox.com/kb/article/476-create-api-key-auth-code-happyfox/) for credentials setup.

---

## CI/CD

Every push to `main` triggers a GitHub Actions workflow that:

1. Builds the Docker image
2. Pushes it to `ghcr.io/glitch3dpenguin/happyfox-mcp` with the following tags:
   - `:latest` — always points to the current `main`
   - `:sha-<commit>` — pinned to a specific commit for traceability
   - `:v2.1.0`, `:v2.1`, `:v2` — on tagged releases

If you're running in Portainer, set up a [webhook](https://docs.portainer.io/user/docker/stacks/webhooks) on your stack to auto-pull `:latest` whenever a new image is pushed.

---

## API Reference

All tools use the **HappyFox v1.1 JSON API** with HTTP Basic Authentication.

Base URL: `https://<HAPPYFOX_DOMAIN>/api/1.1/json/`

Full docs: [HappyFox API Reference](https://support.happyfox.com/kb/article/360-api-for-happyfox/)

---

## Changelog

### v2.1
- **New:** `get_ticket_attachments` — list every attachment on a ticket (opening message + all replies) with ID, type, size, and source message. Falls back to resolving inline `cid:` references when the API returns no structured attachment objects.
- **New:** `download_attachment(ticket_id, attachment_id)` — fetch one attachment; images are returned natively so the agent can view them inline.
- **New:** `list_priorities` + `change_ticket_priority` — escalate/de-escalate tickets.
- **New:** `assign_ticket` — assign or reassign tickets to staff.
- **New:** `change_ticket_category` — move tickets between categories.
- **Changed:** `rename_ticket` is now `suggest_ticket_rename` — posts a private note with a suggested title, because the v1.1 API has no endpoint to rename a subject.
- **Fix:** Suppressed noisy `ClientDisconnect`/Starlette log messages in HTTP transports.
- **Fix:** All HappyFox API calls now use a 30s timeout so tools can't hang indefinitely.
- **Docs:** Corrected the MCP endpoint URL — the server listens at the root path `/`, not `/mcp`.

### v2.0
- **Fix:** `list_tickets` returns a compact summary table instead of raw JSON. Resolves context window overflow ([#1](https://github.com/Glitch3dPenguin/happyfox-mcp/issues/1)).
- **Fix:** Ticket detail/update endpoints corrected from `/tickets/{id}/` to singular `/ticket/{id}/`.
- **Fix:** Private note endpoint corrected from `staff_private_note` to `staff_pvtnote`.
- **Fix:** `create_ticket` payload field renamed from `message` to `text` per API spec.
- **New:** `get_ticket_messages` — fetch conversation thread, most recent N messages.
- **New:** Title rename via private note suggestion (`suggest_ticket_rename` — the API cannot rename subjects directly).
- **New:** `change_ticket_status` — dedicated status-only update.
- **New:** `list_statuses` — look up status names and IDs for your account.
- **New:** `list_staff` — look up agent names and IDs for your account.
- **New:** Streamable HTTP and SSE transport support via `MCP_TRANSPORT` env var.
- **New:** Dockerfile, docker-compose, and GitHub Actions CI/CD pipeline.

### v1.0
- Initial release.

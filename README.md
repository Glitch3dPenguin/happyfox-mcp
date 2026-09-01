<p align="center">
  <img src="assets/HF-MCP-Community-Logo.png" width="96" alt="HappyFox MCP Community logo" />
</p>

<h1 align="center">HappyFox MCP Server</h1>

<p align="center">
  <img src="https://img.shields.io/badge/MCP-stdio%20%C2%B7%20streamable--http%20%C2%B7%20sse-8B5CF6" alt="MCP transports" />
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/HappyFox-API%20v1.1-FF5A00" alt="HappyFox API v1.1" />
  <img src="https://img.shields.io/badge/tools-13%20read%20%C2%B7%2010%20write-FF5A00" alt="23 tools" />
</p>

<p align="center">
  A <a href="https://modelcontextprotocol.io/">Model Context Protocol (MCP)</a> server that connects AI agents to the
  <a href="https://www.happyfox.com/">HappyFox</a> Help Desk API. Designed to be <strong>context-window safe</strong> —
  ticket lists return titles and metadata only, so agents can triage a full queue without blowing out their context.
  Full message bodies are fetched on demand, one ticket at a time.
</p>

<p align="center">
  <strong>Community project</strong> — not affiliated with or endorsed by HappyFox Inc.<br/>
  <a href="#other-happyfox-mcp-options">Other HappyFox MCP options</a> · <a href="https://www.happyfox.com/media-kit/">Brand assets</a>
</p>

---

## Features

- **Context-safe ticket listing** — compact summary table (ID, status, priority, assignee, subject). No message bodies in list output.
- **Queue filters & sorting** — filter tickets by assignee, priority, tags, due date, contact, unresponded and SLA-breached state, plus 20+ sort options (due date, priority, created, updated, ...).
- **On-demand detail fetching** — pull metadata (due date, tags, SLA breaches, time spent, custom fields, contact info) or the full message thread for a single ticket when you need it.
- **Attachment viewing & downloading** — images are returned natively so the agent can see them inline; other files return metadata + URL.
- **Status management** — change ticket status, close tickets, look up all available statuses by ID.
- **Priority & assignment** — escalate/de-escalate priority and assign or reassign tickets to staff.
- **Category management** — move tickets between categories, filter the queue by category.
- **Tags & due dates** — add/remove tags and set or clear ticket due dates.
- **Custom fields** — list ticket custom fields and set ticket/contact custom field values.
- **Contact lookup** — search contacts and inspect their detail: phones, contact groups, ticket counts, custom fields.
- **Connection check** — verify credentials and connectivity before starting work.
- **Draft → confirm pattern** — write tools are designed to be confirmed by the user before posting.
- **Title rename suggestions** — the v1.1 API can't rename subjects, so the agent posts a private note with a suggested title for a human to apply in the UI.
- **Private notes** — post internal staff notes that are never sent to the contact.
- **Full ID lookup** — resolve staff, status, priority, category, and custom-field IDs before acting, no hardcoding values that differ between accounts.

---

## Tools

### Read Tools

| Tool | Description |
|---|---|
| `check_connection` | Verify credentials and connectivity, with a quick account summary. Run first when debugging a new setup. |
| `list_tickets` | Compact table of tickets — titles and metadata only. Filters: status, free-form query, category, assignee, priority, tags, due date, contact, unresponded, SLA-breached. 20+ sort options. |
| `get_ticket_details` | Structured metadata for one ticket — incl. due date, tags, SLA breaches, time spent, last replies, contact phone/groups/ticket counts, and custom field values — plus truncated opening message. |
| `get_ticket_messages` | Conversation thread for one ticket. Returns the most recent N messages (default 5), or the first N with `from_start=true` for long threads. |
| `get_ticket_attachments(ticket_id)` | List all attachments on a ticket (opening message + every reply) with IDs, types, sizes, and which message each came from. |
| `download_attachment(ticket_id, attachment_id)` | Fetch one attachment. Images (PNG/JPG/GIF/WEBP) are returned natively so the agent can view them; other file types return metadata + URL. |
| `list_statuses` | All statuses in your HappyFox account with their IDs. |
| `list_categories` | All ticket categories with their IDs (for `list_tickets` filtering and `change_ticket_category`). |
| `list_priorities` | All ticket priorities with their IDs and names (for `change_ticket_priority` and `list_tickets(priority=...)`). |
| `list_staff` | All staff/agents with their IDs. |
| `list_ticket_custom_fields` | All ticket custom fields with IDs, types, and choice options (for `update_ticket_custom_fields`). |
| `list_contacts` | List/search contacts (customers) with pending/total ticket counts. |
| `get_contact` | Full detail for one contact by ID or email: phones, groups, ticket counts, custom fields. |

### Write Tools

| Tool | Description |
|---|---|
| `add_ticket_update` | Post a public reply or private internal note to a ticket. Optionally change status in the same call; public replies support CC/BCC and launching a satisfaction survey. |
| `create_ticket` | Open a new support ticket, optionally with priority, assignee, phone, tags, due date, and CC. |
| `suggest_ticket_rename(ticket_id, suggested_subject, staff_id)` | Post a private note suggesting a better title (the v1.1 API cannot rename subjects — an agent applies it in the UI). |
| `change_ticket_status` | Change ticket status only (e.g. close, put on hold). |
| `assign_ticket` | Assign or reassign a ticket to a staff member. |
| `change_ticket_priority` | Change ticket priority (e.g. escalate to Urgent). |
| `change_ticket_category` | Move a ticket into a different category. |
| `update_ticket_tags(ticket_id, staff_id, add, remove)` | Add and/or remove comma-separated tags on a ticket. |
| `set_ticket_due_date(ticket_id, due_date, staff_id)` | Set a ticket due date (yyyy-mm-dd) or clear it with an empty string. |
| `update_ticket_custom_fields(ticket_id, staff_id, fields)` | Set ticket (`t-cf-<id>`) and contact (`c-cf-<id>`) custom field values. |

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

## Other HappyFox MCP options

This is a **community project**. As of August 2026, HappyFox Inc. does not ship an official MCP server on any plan —
its [AI product](https://www.happyfox.com/happyfox-ai/) and [integrations catalog](https://www.happyfox.com/helpdesk/integrations/)
cover in-product AI and 100+ app integrations, but there is no MCP endpoint of their own. Every HappyFox MCP
integration is third-party, and this is not the only one:

| Option | Type | What it is |
|---|---|---|
| **This server** | Self-hosted | Context-safe MCP server for the HappyFox v1.1 API — stdio, Streamable HTTP, and SSE, with a Docker image on GHCR. |
| [Zapier MCP](https://zapier.com/mcp/happyfox) | Hosted | HappyFox access through Zapier's general-purpose MCP connector. |
| [viaSocket](https://viasocket.com/mcp/happyfox) | Hosted | Hosted MCP endpoint with a no-code configuration UI. |
| [leoherzog/happyfox-mcp](https://github.com/leoherzog/happyfox-mcp) | Self-hosted | Another open-source implementation, deployed as a Cloudflare Worker. |

If you just need a hosted endpoint, one of the above may save you the ops work. This server is for teams that want
their own credentials, their own infrastructure, and a queue-friendly read model.

---

## Branding & trademarks

HappyFox and the HappyFox logo are trademarks of HappyFox Inc. This project is **not affiliated with, endorsed by,
or sponsored by** HappyFox Inc. The logo above is this community project's own artwork — no HappyFox media-kit
assets are used. "HappyFox" is always written as a single word with an uppercase H and F.

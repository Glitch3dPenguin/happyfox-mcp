# HappyFox MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that connects AI agents to the HappyFox Help Desk API. Designed to be **context-window safe** — ticket lists return titles and metadata only, so agents can triage a full queue without blowing out their context. Full message bodies are fetched on demand, one ticket at a time.

Built on the HappyFox v1.1 JSON API using `stdio` transport.

---

## Features

- **Context-safe ticket listing** — returns a compact summary table (ID, status, priority, assignee, subject). No message bodies in list output.
- **On-demand detail fetching** — pull metadata or the full message thread for a single ticket when you actually need it.
- **Status management** — change ticket status, close tickets, or look up all available statuses by ID.
- **Draft → confirm pattern** — write tools (replies, notes, status changes) are designed to be confirmed by the user before posting.
- **Ticket renaming** — let an agent retitle vague subjects like "Help!!" to something meaningful.
- **Private notes** — post internal staff notes that are never sent to the contact.
- **Full staff/category lookup** — resolve IDs before acting, rather than hardcoding values that differ between accounts.

---

## Tools

### Read Tools

| Tool | Description |
|---|---|
| `list_tickets` | Compact table of tickets — titles and metadata only. Supports filtering by status, search query, and pagination. |
| `get_ticket_details` | Structured metadata + truncated opening message for one ticket. |
| `get_ticket_messages` | Full conversation thread for one ticket. Returns the most recent N messages (default 5). |
| `list_statuses` | All statuses configured in your HappyFox account with their IDs. |
| `list_staff` | All staff/agents with their IDs. |

### Write Tools

> ⚠️ All write tools should be confirmed with the user before executing. Replies and status changes are immediate and cannot be undone through the API.

| Tool | Description |
|---|---|
| `add_ticket_update` | Post a public reply or private internal note to a ticket. Optionally change status in the same call. |
| `create_ticket` | Open a new support ticket. |
| `rename_ticket` | Update a ticket's subject/title. |
| `change_ticket_status` | Change ticket status only (e.g. close, put on hold). |

---

## Recommended Agent Workflow

```
1. list_tickets()                        # Get a summary of open tickets
2. get_ticket_details(ticket_id)         # Read metadata for a specific ticket
3. get_ticket_messages(ticket_id)        # Read the conversation thread
4. [show draft reply to user for approval]
5. add_ticket_update(ticket_id, ...)     # Post the approved reply
```

For status changes:
```
1. list_statuses()                       # Find the correct status ID
2. list_staff()                          # Find your staff ID
3. change_ticket_status(id, status_id, staff_id)
```

---

## Installation

**1. Clone the repository:**

```bash
git clone https://github.com/Glitch3dPenguin/happyfox-mcp.git
cd happyfox-mcp
```

**2. Install dependencies:**

```bash
pip install -r requirements.txt
```

**3. Set environment variables:**

```bash
export HAPPYFOX_DOMAIN="yourcompany.happyfox.com"
export HAPPYFOX_API_KEY="your_api_key"
export HAPPYFOX_AUTH_CODE="your_auth_code"
```

See [Generating and Managing API Authentication Keys](https://support.happyfox.com/kb/article/476-create-api-key-auth-code-happyfox/) for how to get your API key and auth code.

> **EU accounts:** Use `yourcompany.happyfox.net` instead of `.com`.

---

## AI Client Configuration

### GUI-based clients (Claude Desktop, Cursor, etc.)

| Field | Value |
|---|---|
| **Name** | `HappyFox` |
| **Transport** | `stdio` |
| **Command** | `python` (or `python3`) |
| **Args** | `["/absolute/path/to/happyfox_mcp.py"]` |
| **Env** | `{ "HAPPYFOX_DOMAIN": "...", "HAPPYFOX_API_KEY": "...", "HAPPYFOX_AUTH_CODE": "..." }` |

> **⚠️ The `Args` path must be absolute.** AI clients cannot resolve relative paths.
>
> - Windows: `["C:\\Users\\Name\\Documents\\happyfox-mcp\\happyfox_mcp.py"]`
> - Mac/Linux: `["/home/username/happyfox-mcp/happyfox_mcp.py"]`

### `claude_desktop_config.json` example

```json
{
  "mcpServers": {
    "happyfox": {
      "command": "python3",
      "args": ["/absolute/path/to/happyfox_mcp.py"],
      "env": {
        "HAPPYFOX_DOMAIN": "yourcompany.happyfox.com",
        "HAPPYFOX_API_KEY": "your_api_key",
        "HAPPYFOX_AUTH_CODE": "your_auth_code"
      }
    }
  }
}
```

---

## API Reference

All tools use the **HappyFox v1.1 JSON API** with HTTP Basic Authentication (API key + auth code).

Base URL format: `https://<HAPPYFOX_DOMAIN>/api/1.1/json/`

Full API documentation: [HappyFox API Reference](https://support.happyfox.com/kb/article/360-api-for-happyfox/)

---

## Changelog

### v2.0
- **Fix:** `list_tickets` now returns a compact summary table instead of raw JSON. Resolves context window overflow with large queues ([#1](https://github.com/Glitch3dPenguin/happyfox-mcp/issues/1)).
- **Fix:** `get_ticket_details` was calling `/tickets/{id}/` — corrected to singular `/ticket/{id}/`.
- **Fix:** Private note endpoint was `staff_private_note` — corrected to `staff_pvtnote`.
- **Fix:** `create_ticket` payload field renamed from `message` to `text` to match the API spec.
- **New:** `get_ticket_messages` — fetch just the conversation thread, most recent N messages.
- **New:** `rename_ticket` — update a ticket's subject/title.
- **New:** `change_ticket_status` — dedicated status-only update tool.
- **New:** `list_statuses` — look up status names and IDs for your account.
- **New:** `list_staff` — look up agent names and IDs for your account.

### v1.0
- Initial release with `list_tickets`, `get_ticket_details`, `create_ticket`, `add_ticket_update`.

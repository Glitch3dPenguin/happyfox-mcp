# HappyFox MCP Server

A Model Context Protocol (MCP) server that enables AI agents to manage, read, and respond to tickets within the HappyFox Ticketing system.

## 🚀 Features
- **Ticket Discovery**: List and search for tickets using filters.
- **Deep Dive**: Retrieve full history and metadata for any ticket.
- **Lifecycle Management**: Create new tickets and update status (e.g., move a ticket to "Closed" or "Resolved").
- **Drafting Workflow**: Use internal private notes as drafts before posting public responses to customers.
- **System Discovery**: Dynamically fetch Statuses and Categories IDs to ensure accurate updates across different HappyFox accounts.

## 🛠️ Installation & Setup

### 1. Environment Variables
The server requires the following environment variables for authentication:
- `HAPPYFOX_DOMAIN`: Your account domain (e.g., `yourcompany.happyfox.com`).
- `HAPPYFOX_API_KEY`: Your HappyFox API key.
- `HAPPYFOX_AUTH_CODE`: Your HappyFox API authentication code.

### 2. Dependencies
Ensure you have Python installed, then install the required libraries:
```bash
pip install requests mcp
```

## 🖥️ Platform Configuration: Odysseus

To add this server to the **Odysseus** platform, use these settings in the "Add MCP Server" dialog:

| Field | Value |
| :--- | :--- |
| **Name** | `HappyFox` |
| **Transport** | `stdio` |
| **Command** | `python` (or `python3`) |
| **Args** | `["/absolute/path/to/your/happyfox-mcp/happyfox_mcp.py"]` |

**Copy-Paste Args String:**  
`["/absolute/path/to/your/happyfox-mcp/happyfox_mcp.py"]` *(Replace with your actual local path)*

### Environment Setup (Env section)
Pass your credentials as a JSON object:
```json
{
  "HAPPYFOX_DOMAIN": "yourcompany.happyfox.com",
  "HAPPYFOX_API_KEY": "your_api_key",
  "HAPPYFOX_AUTH_CODE": "your_auth_code"
}
```

## 🤖 Agent Guidance (Drafting & Closing)
To ensure a high-quality support experience, agents should follow this logic:
1. **Drafting**: When responding to a customer, use `add_ticket_update` with `is_private=True`. This saves the response as an internal note for review.
2. **Confirmation**: Ask the human user to review the private note draft.
3. **Publishing**: Once approved, call `add_ticket_update` again with `is_private=False`.
4. **Closing**: Use `list_statuses` to find the ID for "Closed" or "Resolved", then use `update_ticket(status_id=...)` to close the ticket.

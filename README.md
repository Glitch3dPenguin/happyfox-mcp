# HappyFox MCP Server

This is a Model Context Protocol (MCP) server that allows AI agents to interact with the HappyFox Ticketing API via stdio.

## Features
- List tickets with filtering and search.
- Retrieve full details for specific tickets.
- Create new support tickets.
- Add public updates or private internal notes to existing tickets.
- Update ticket attributes (Status, Priority, Category).
- Discover available statuses and categories from the system.

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/Glitch3dPenguin/happyfox-mcp.git
   cd happyfox-mcp
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Native AI Client Configuration (GUI)

If you are using an AI client with a GUI for adding MCP servers, enter the following:

| Field | Value |
| :--- | :--- |
| **Name** | `HappyFox` |
| **Transport** | `stdio` |
| **Command** | `python` (or `python3`) |
| **Args** | `["/absolute/path/to/happyfox_mcp.py"]` |
| **Env** | `{ "HAPPYFOX_DOMAIN": "...", "HAPPYFOX_API_KEY": "...", "HAPPYFOX_AUTH_CODE": "..." }` |

### ⚠️ Critical Note on Paths:
The `Args` field **must** be the absolute path to the file. The AI client cannot resolve relative paths.
- Windows Example: `["C:\\Users\\Name\\Documents\\happyfox_mcp.py"]`
- Mac/Linux Example: `["/home/username/happyfox_mcp.py"]`

## API Version
Implemented using the HappyFox v1.1 JSON API.

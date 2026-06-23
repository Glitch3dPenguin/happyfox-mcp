import os
import json
import textwrap
import requests
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server init
# host/port are set here so FastMCP's uvicorn runner picks them up correctly.
# These args live on the constructor, NOT on .run() — that's the API contract.
# ---------------------------------------------------------------------------
_transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
_host      = "0.0.0.0" if _transport in ("streamable-http", "sse") else "127.0.0.1"
_port      = int(os.getenv("PORT", "8000"))

mcp = FastMCP("HappyFox", host=_host, port=_port)

# ---------------------------------------------------------------------------
# Configuration (from environment variables)
# ---------------------------------------------------------------------------
HAPPYFOX_DOMAIN = os.getenv("HAPPYFOX_DOMAIN")   # e.g. "acme.happyfox.com"
API_KEY         = os.getenv("HAPPYFOX_API_KEY")
AUTH_CODE       = os.getenv("HAPPYFOX_AUTH_CODE")
BASE_URL        = f"https://{HAPPYFOX_DOMAIN}/api/1.1/json"

def _auth():
    """Basic-auth tuple expected by every HappyFox request."""
    return (API_KEY, AUTH_CODE)

def _truncate(text: str, max_chars: int = 300) -> str:
    """Return text truncated to max_chars with an ellipsis note if cut."""
    if not text:
        return "(empty)"
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"… [truncated – {len(text) - max_chars} more chars]"

# ===========================================================================
# READ TOOLS
# ===========================================================================

@mcp.tool()
def list_tickets(
    status: str = "_pending",
    query:  str = "",
    page:   int = 1,
    size:   int = 20,
) -> str:
    """
    Return a compact, agent-friendly summary of tickets – titles and key
    metadata ONLY.  No message bodies are included so this never blows out
    a context window.

    Use get_ticket_details() or get_ticket_messages() to drill into a
    specific ticket once you have its ID.

    Args:
        status: '_pending' (default), '_all', '_completed', or a numeric
                status ID string.  Use list_statuses() to see valid values.
        query:  Optional HappyFox search string (same syntax as the UI).
        page:   Page number (1-based).
        size:   Tickets per page (1-50, default 20).
    """
    url = f"{BASE_URL}/tickets/"
    params = {
        "status": status,
        "q":      query,
        "page":   page,
        "size":   min(size, 50),
        # Note: HappyFox ignores the 'fields' param on most accounts, so we
        # receive the full response and manually extract only what we need
        # before returning – keeping agent output compact regardless.
    }
    r = requests.get(url, auth=_auth(), params=params)
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    data = r.json()
    page_info = data.get("page_info", {})
    tickets   = data.get("data", [])

    if not tickets:
        return "No tickets found matching those criteria."

    lines = [
        f"Tickets (page {page}/{page_info.get('page_count', '?')}, "
        f"total: {page_info.get('count', '?')})",
        "",
        f"{'ID':<8} {'Display ID':<14} {'Status':<14} {'Priority':<10} "
        f"{'Assignee':<20} {'Subject'}",
        "-" * 100,
    ]

    for t in tickets:
        tid        = t.get("id", "")
        display_id = t.get("display_id", "")
        subject    = t.get("subject", "(no subject)")
        status_nm  = t.get("status", {}).get("name", "?") if isinstance(t.get("status"), dict) else str(t.get("status", ""))
        priority   = t.get("priority", {}).get("name", "?") if isinstance(t.get("priority"), dict) else ""
        assignee   = ""
        if isinstance(t.get("assigned_to"), dict):
            assignee = t["assigned_to"].get("name", "Unassigned")
        elif t.get("assigned_to") is None:
            assignee = "Unassigned"

        # Truncate long subjects so the table stays readable
        short_subject = subject if len(subject) <= 55 else subject[:52] + "..."

        lines.append(
            f"{str(tid):<8} {display_id:<14} {status_nm:<14} {priority:<10} "
            f"{assignee:<20} {short_subject}"
        )

    lines += [
        "",
        f"Use get_ticket_details(ticket_id) to read a specific ticket.",
        f"Use list_tickets(page={page+1}) to see the next page." if page_info.get("page_count", 1) > page else "",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_ticket_details(ticket_id: int) -> str:
    """
    Return structured metadata and the opening message for ONE ticket.
    Message bodies are truncated to keep the response concise.

    Call get_ticket_messages(ticket_id) separately to read the full
    conversation thread.

    Args:
        ticket_id: The numeric ticket ID (the 'id' column from list_tickets).
    """
    # NOTE: singular /ticket/ not /tickets/  ← this was the bug in v1
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r = requests.get(url, auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    t = r.json()

    assignee = "Unassigned"
    if isinstance(t.get("assigned_to"), dict):
        assignee = t["assigned_to"].get("name", "Unassigned")

    lines = [
        "=" * 60,
        f"Ticket #{ticket_id}  {t.get('display_id', '')}",
        "=" * 60,
        f"Subject   : {t.get('subject', '(no subject)')}",
        f"Status    : {t.get('status', {}).get('name', '?')}  (id={t.get('status', {}).get('id', '?')})",
        f"Priority  : {t.get('priority', {}).get('name', '?')}  (id={t.get('priority', {}).get('id', '?')})",
        f"Category  : {t.get('category', {}).get('name', '?')}  (id={t.get('category', {}).get('id', '?')})",
        f"Assignee  : {assignee}",
        f"Contact   : {t.get('user', {}).get('name', '?')} <{t.get('user', {}).get('email', '?')}>",
        f"Created   : {t.get('created_at', '?')}",
        f"Updated   : {t.get('last_updated_at', '?')}",
        f"Messages  : {t.get('messages_count', 0)}  (use get_ticket_messages to read them)",
        f"Attachments: {t.get('attachments_count', 0)}",
        "",
        "--- Opening Message ---",
        _truncate(t.get("first_message", ""), max_chars=600),
        "",
        "Tip: call get_ticket_messages(ticket_id) to read the full thread.",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_ticket_messages(ticket_id: int, max_messages: int = 5) -> str:
    """
    Return the conversation thread for a ticket – the most recent N messages.

    Each message is shown in full (not truncated) so you can draft replies
    with full context.  Keep max_messages small to avoid filling the context
    window.

    Args:
        ticket_id:    Numeric ticket ID.
        max_messages: How many of the most-recent updates to return (default 5).
    """
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r = requests.get(url, auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    t       = r.json()
    updates = t.get("updates", [])

    if not updates:
        return f"Ticket #{ticket_id} has no message updates yet."

    # Most-recent first, then slice
    recent = updates[-max_messages:]

    lines = [
        f"Last {len(recent)} of {len(updates)} messages in ticket #{ticket_id} "
        f"({t.get('display_id', '')}): {t.get('subject', '')}",
        "",
    ]
    for i, upd in enumerate(recent, 1):
        by      = upd.get("by", {})
        author  = f"{by.get('name', '?')} ({by.get('type', '?')})"
        ts      = upd.get("timestamp", "?")
        msg     = upd.get("message", {})
        body    = msg.get("text") or msg.get("html") or "(no body)"

        # Strip HTML tags crudely if html-only
        if msg.get("html") and not msg.get("text"):
            import re
            body = re.sub(r"<[^>]+>", "", body).strip()

        lines += [
            f"[{i}] {ts}  —  {author}",
            body.strip(),
            "",
        ]

    return "\n".join(lines)


@mcp.tool()
def list_statuses() -> str:
    """
    List all ticket statuses configured in HappyFox with their IDs.

    Use the status ID when closing a ticket or changing its status via
    add_ticket_update().
    """
    r = requests.get(f"{BASE_URL}/statuses/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    statuses = r.json()
    lines = ["Available Statuses:", ""]
    for s in statuses:
        lines.append(
            f"  id={s['id']:<4}  behavior={s.get('behavior','?'):<12}  name={s['name']}"
        )
    return "\n".join(lines)


@mcp.tool()
def list_staff() -> str:
    """
    List all staff/agents with their IDs.

    The staff ID is required when posting updates or private notes.
    """
    r = requests.get(f"{BASE_URL}/staff/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    staff = r.json()
    lines = ["Staff / Agents:", ""]
    for s in staff:
        active = "active" if s.get("active") else "inactive"
        lines.append(f"  id={s['id']:<4}  {active:<8}  {s.get('name','?')}  <{s.get('email','?')}>")
    return "\n".join(lines)


# ===========================================================================
# WRITE TOOLS  (draft → confirm pattern)
# ===========================================================================

@mcp.tool()
def add_ticket_update(
    ticket_id:      int,
    message:        str,
    staff_id:       int,
    is_private:     bool = False,
    status_id:      int  = None,
    notify_contact: bool = True,
) -> str:
    """
    Post a reply or private note to a ticket.

    IMPORTANT: Always show the exact message text to the user and get their
    explicit approval before calling this tool.  Replies are sent immediately
    and cannot be unsent.

    Args:
        ticket_id:      Numeric ticket ID.
        message:        The reply or note body (plain text).
        staff_id:       ID of the staff member posting the update (from list_staff).
        is_private:     If True, posts as a private internal note (not sent to
                        the contact).  Default False (public reply).
        status_id:      Optional status ID to set at the same time (e.g. to
                        close the ticket).  Use list_statuses() to find IDs.
        notify_contact: Whether to email the contact.  Ignored for private notes.
    """
    if is_private:
        # NOTE: correct endpoint is staff_pvtnote, NOT staff_private_note ← was the v1 bug
        endpoint = f"{BASE_URL}/ticket/{ticket_id}/staff_pvtnote/"
        payload  = {
            "staff":     staff_id,
            "plaintext": message,
        }
    else:
        endpoint = f"{BASE_URL}/ticket/{ticket_id}/staff_update/"
        payload  = {
            "staff":           staff_id,
            "plaintext":       message,
            "update_customer": notify_contact,
        }

    if status_id is not None:
        payload["status"] = status_id

    r = requests.post(endpoint, auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        kind = "Private note" if is_private else "Reply"
        result = f"{kind} posted successfully to ticket #{ticket_id}."
        if status_id is not None:
            result += f"  Status changed to id={status_id}."
        return result

    return f"Error {r.status_code}: {r.text}"


@mcp.tool()
def create_ticket(
    subject:       str,
    message:       str,
    contact_name:  str,
    contact_email: str,
    category_id:   int,
    priority_id:   int = None,
    assignee_id:   int = None,
) -> str:
    """
    Create a new support ticket.

    IMPORTANT: Confirm all details with the user before calling this.

    Args:
        subject:       Ticket subject line.
        message:       Opening message body (plain text).
        contact_name:  Name of the contact the ticket is for.
        contact_email: Email address of the contact.
        category_id:   HappyFox category ID (use list_categories if unsure).
        priority_id:   Optional priority ID.
        assignee_id:   Optional staff ID to assign immediately.
    """
    url     = f"{BASE_URL}/tickets/"
    payload = {
        "subject":  subject,
        "text":     message,   # NOTE: field is 'text', not 'message'  ← v1 bug
        "name":     contact_name,
        "email":    contact_email,
        "category": category_id,
    }
    if priority_id is not None:
        payload["priority"] = priority_id
    if assignee_id is not None:
        payload["assignee"] = assignee_id

    r = requests.post(url, auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        created = r.json()
        return (
            f"Ticket created: #{created.get('id')}  {created.get('display_id')}  "
            f"— {created.get('subject')}"
        )
    return f"Error {r.status_code}: {r.text}"


@mcp.tool()
def rename_ticket(ticket_id: int, new_subject: str, staff_id: int) -> str:
    """
    Rename a ticket's subject/title.

    Useful when the original subject is vague (e.g. 'Help!', 'Question') and
    makes it hard for an agent or AI to know what the ticket is about at a
    glance.

    IMPORTANT: Confirm the new title with the user before calling this.

    Args:
        ticket_id:   Numeric ticket ID.
        new_subject: The new subject / title to set.
        staff_id:    ID of the staff member making the change (from list_staff).
    """
    # The staff_update endpoint accepts a 'subject' field to change the ticket title.
    url     = f"{BASE_URL}/ticket/{ticket_id}/staff_update/"
    payload = {
        "staff":   staff_id,
        "subject": new_subject,
    }
    r = requests.post(url, auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        return f"Ticket #{ticket_id} subject updated to: \"{new_subject}\""
    return f"Error {r.status_code}: {r.text}"


@mcp.tool()
def change_ticket_status(ticket_id: int, status_id: int, staff_id: int) -> str:
    """
    Change the status of a ticket (e.g. close it, put it on hold).

    Use list_statuses() to find the correct status ID first.

    Args:
        ticket_id: Numeric ticket ID.
        status_id: ID of the new status (from list_statuses).
        staff_id:  ID of the staff member making the change (from list_staff).
    """
    url     = f"{BASE_URL}/ticket/{ticket_id}/staff_update/"
    payload = {
        "staff":  staff_id,
        "status": status_id,
    }
    r = requests.post(url, auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        return f"Ticket #{ticket_id} status changed to id={status_id}."
    return f"Error {r.status_code}: {r.text}"


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    # host/port were already passed to the FastMCP() constructor above.
    # .run() only accepts 'transport' — host/port here would raise TypeError.
    mcp.run(transport=_transport)

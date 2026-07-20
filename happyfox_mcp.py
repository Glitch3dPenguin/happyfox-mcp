import os
import re
import requests
from mcp.server.fastmcp import FastMCP, Image

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
_transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
_host      = "0.0.0.0" if _transport in ("streamable-http", "sse") else "127.0.0.1"
_port      = int(os.getenv("PORT", "8000"))

mcp = FastMCP(
    "HappyFox",
    host=_host,
    port=_port,
    streamable_http_path="/",
    sse_path="/sse",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HAPPYFOX_DOMAIN = os.getenv("HAPPYFOX_DOMAIN")
API_KEY         = os.getenv("HAPPYFOX_API_KEY")
AUTH_CODE       = os.getenv("HAPPYFOX_AUTH_CODE")
BASE_URL        = f"https://{HAPPYFOX_DOMAIN}/api/1.1/json"

def _auth():
    return (API_KEY, AUTH_CODE)

def _truncate(text: str, max_chars: int = 300) -> str:
    if not text:
        return "(empty)"
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [truncated - {len(text) - max_chars} more chars]"

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()

def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def _collect_attachments(ticket_data: dict) -> list:
    """Collect all attachments from all parts of a ticket response."""
    all_attachments = []
    seen_ids = set()

    def add(a, source):
        aid = a.get("id")
        if aid not in seen_ids:
            seen_ids.add(aid)
            all_attachments.append({**a, "_source": source})

    # Opening message
    first_msg = ticket_data.get("first_message", {})
    if isinstance(first_msg, dict):
        for a in first_msg.get("attachments", []):
            add(a, "Opening message")
    # Top-level fallback (some API versions put them here)
    for a in ticket_data.get("attachments", []):
        add(a, "Opening message")

    # Updates / replies
    for idx, upd in enumerate(ticket_data.get("updates", []), 1):
        ts  = upd.get("timestamp", f"update #{idx}")
        msg = upd.get("message", {}) or {}
        for a in list(msg.get("attachments") or []) + list(upd.get("attachments") or []):
            add(a, f"Reply {idx} ({ts})")

    return all_attachments


# ===========================================================================
# READ TOOLS
# ===========================================================================

@mcp.tool()
def list_tickets(
    status:      str = "_pending",
    query:       str = "",
    page:        int = 1,
    size:        int = 20,
    category_id: int = None,
) -> str:
    """
    Return a compact, agent-friendly summary of tickets - titles and key
    metadata ONLY. No message bodies included so this never blows out context.

    Use get_ticket_details() or get_ticket_messages() to drill into a ticket.
    Use get_ticket_attachments() to list files on a ticket.

    Args:
        status:      '_pending' (default), '_all', '_completed', or a numeric
                     status ID. Use list_statuses() to see valid values.
        query:       Optional HappyFox search string.
        page:        Page number (1-based).
        size:        Tickets per page (1-50, default 20).
        category_id: Optional category ID to filter. Use list_categories() for IDs.
    """
    url    = f"{BASE_URL}/tickets/"
    params = {"status": status, "q": query, "page": page, "size": min(size, 50)}
    if category_id is not None:
        params["category"] = category_id

    r = requests.get(url, auth=_auth(), params=params)
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    data      = r.json()
    page_info = data.get("page_info", {})
    tickets   = data.get("data", [])

    if not tickets:
        return "No tickets found matching those criteria."

    header = (f"Tickets (page {page}/{page_info.get('page_count', '?')}, "
              f"total: {page_info.get('count', '?')})")
    if category_id is not None:
        header += f"  [category id={category_id}]"

    lines = [
        header, "",
        f"{'ID':<8} {'Display ID':<14} {'Status':<14} {'Priority':<10} {'Attach':<7} {'Assignee':<20} {'Subject'}",
        "-" * 108,
    ]

    for t in tickets:
        tid        = t.get("id", "")
        display_id = t.get("display_id", "")
        subject    = t.get("subject", "(no subject)")
        status_nm  = (t.get("status", {}).get("name", "?")
                      if isinstance(t.get("status"), dict) else str(t.get("status", "")))
        priority   = (t.get("priority", {}).get("name", "?")
                      if isinstance(t.get("priority"), dict) else "")
        assignee   = "Unassigned"
        if isinstance(t.get("assigned_to"), dict):
            assignee = t["assigned_to"].get("name", "Unassigned")
        attach_ct  = t.get("attachments_count", 0)
        attach_col = f"{attach_ct} file" if attach_ct == 1 else (f"{attach_ct} files" if attach_ct else "")
        short_subj = subject if len(subject) <= 48 else subject[:45] + "..."

        lines.append(
            f"{str(tid):<8} {display_id:<14} {status_nm:<14} {priority:<10} "
            f"{attach_col:<7} {assignee:<20} {short_subj}"
        )

    lines += ["", "Use get_ticket_details(ticket_id) to read a specific ticket."]
    if page_info.get("page_count", 1) > page:
        lines.append(f"Use list_tickets(page={page + 1}) for the next page.")
    return "\n".join(lines)


@mcp.tool()
def get_ticket_details(ticket_id: int) -> str:
    """
    Return structured metadata and truncated opening message for ONE ticket.

    Call get_ticket_messages(ticket_id) for the full thread.
    Call get_ticket_attachments(ticket_id) to list and download files.

    Args:
        ticket_id: Numeric ticket ID (the 'id' column from list_tickets).
    """
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r   = requests.get(url, auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    t        = r.json()
    assignee = "Unassigned"
    if isinstance(t.get("assigned_to"), dict):
        assignee = t["assigned_to"].get("name", "Unassigned")

    attach_count = t.get("attachments_count", 0)
    attach_hint  = (f"{attach_count}  (call get_ticket_attachments to list + download)"
                    if attach_count > 0 else "0")

    lines = [
        "=" * 60,
        f"Ticket #{ticket_id}  {t.get('display_id', '')}",
        "=" * 60,
        f"Subject    : {t.get('subject', '(no subject)')}",
        f"Status     : {t.get('status', {}).get('name', '?')}  (id={t.get('status', {}).get('id', '?')})",
        f"Priority   : {t.get('priority', {}).get('name', '?')}  (id={t.get('priority', {}).get('id', '?')})",
        f"Category   : {t.get('category', {}).get('name', '?')}  (id={t.get('category', {}).get('id', '?')})",
        f"Assignee   : {assignee}",
        f"Contact    : {t.get('user', {}).get('name', '?')} <{t.get('user', {}).get('email', '?')}>",
        f"Created    : {t.get('created_at', '?')}",
        f"Updated    : {t.get('last_updated_at', '?')}",
        f"Messages   : {t.get('messages_count', 0)}  (call get_ticket_messages to read)",
        f"Attachments: {attach_hint}",
        "",
        "--- Opening Message ---",
        _truncate(t.get("first_message", ""), max_chars=600),
    ]
    return "\n".join(lines)


@mcp.tool()
def get_ticket_messages(ticket_id: int, max_messages: int = 5) -> str:
    """
    Return the conversation thread for a ticket - the most recent N messages.

    Attachment names are noted inline; use download_attachment() to fetch them.

    Args:
        ticket_id:    Numeric ticket ID.
        max_messages: How many of the most-recent updates to return (default 5).
    """
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r   = requests.get(url, auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    t       = r.json()
    updates = t.get("updates", [])
    if not updates:
        return f"Ticket #{ticket_id} has no message updates yet."

    recent = updates[-max_messages:]
    lines  = [
        f"Last {len(recent)} of {len(updates)} messages in ticket #{ticket_id} "
        f"({t.get('display_id', '')}): {t.get('subject', '')}",
        "",
    ]
    for i, upd in enumerate(recent, 1):
        by     = upd.get("by", {})
        author = f"{by.get('name', '?')} ({by.get('type', '?')})"
        ts     = upd.get("timestamp", "?")
        msg    = upd.get("message", {})
        body   = msg.get("text") or ""
        if not body and msg.get("html"):
            body = _strip_html(msg["html"])
        if not body:
            body = "(no body)"

        attachments = list(msg.get("attachments") or []) + list(upd.get("attachments") or [])
        attach_note = ""
        if attachments:
            names = ", ".join(f"{a.get('name','?')} (id={a.get('id','?')})" for a in attachments)
            attach_note = f"\n  Attachments: {names}  -> call download_attachment({ticket_id}, <id>)"

        lines += [f"[{i}] {ts}  -  {author}{attach_note}", body.strip(), ""]

    return "\n".join(lines)


@mcp.tool()
def get_ticket_attachments(ticket_id: int) -> str:
    """
    List ALL attachments on a ticket - from the opening message and every
    reply - with IDs, sizes, types, and which message they came from.

    Then call download_attachment(ticket_id, attachment_id) to fetch one.
    Images are returned directly so the agent can view them.

    Args:
        ticket_id: Numeric ticket ID.
    """
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r   = requests.get(url, auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    t               = r.json()
    all_attachments = _collect_attachments(t)

    if not all_attachments:
        return (f"Ticket #{ticket_id} ({t.get('display_id', '')}) has no attachments.\n"
                f"(attachments_count from API: {t.get('attachments_count', 0)})")

    lines = [
        f"Attachments on ticket #{ticket_id} ({t.get('display_id', '')}): {t.get('subject', '')}",
        "",
        f"{'#':<4} {'ID':<8} {'Type':<22} {'Size':<10} {'Source':<32} Name",
        "-" * 110,
    ]
    for i, a in enumerate(all_attachments, 1):
        aid   = a.get("id", "?")
        name  = a.get("name", "?")
        ftype = a.get("type") or a.get("content_type") or "unknown"
        size  = _fmt_size(a.get("size", 0))
        src   = a.get("_source", "?")
        lines.append(f"{i:<4} {str(aid):<8} {ftype:<22} {size:<10} {src:<32} {name}")

    lines += [
        "",
        f"Total: {len(all_attachments)} attachment(s)",
        "",
        "To view/download: download_attachment(ticket_id, attachment_id)",
        "Images (PNG/JPG/GIF/WEBP) are returned directly for the agent to view.",
    ]
    return "\n".join(lines)


@mcp.tool()
def download_attachment(ticket_id: int, attachment_id: int):
    """
    Download a specific attachment from a ticket.

    Images (PNG, JPG, GIF, WEBP) are returned as native image content so the
    agent can view them directly. Other file types return metadata + URL.

    Get attachment IDs from get_ticket_attachments(ticket_id).

    Args:
        ticket_id:     Numeric ticket ID.
        attachment_id: Attachment ID from get_ticket_attachments.
    """
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r   = requests.get(url, auth=_auth())
    if r.status_code != 200:
        return f"Error fetching ticket {ticket_id}: {r.status_code} {r.text}"

    all_attachments = _collect_attachments(r.json())
    target = next((a for a in all_attachments if a.get("id") == attachment_id), None)

    if not target:
        return (f"Attachment id={attachment_id} not found on ticket #{ticket_id}. "
                f"Run get_ticket_attachments({ticket_id}) to see valid IDs.")

    name   = target.get("name", "file")
    ftype  = target.get("type") or target.get("content_type") or ""
    size   = target.get("size", 0)
    dl_url = target.get("url") or target.get("download_url") or ""

    if not dl_url:
        return (f"Attachment '{name}' (id={attachment_id}) has no download URL in the API response. "
                f"Size: {_fmt_size(size)}, Type: {ftype}")

    # Download — try with auth first, then without (pre-signed URLs don't need it)
    dl = requests.get(dl_url, auth=_auth(), timeout=30)
    if dl.status_code != 200:
        dl = requests.get(dl_url, timeout=30)
    if dl.status_code != 200:
        return (f"Error downloading '{name}': HTTP {dl.status_code}.\n"
                f"Direct URL (requires HappyFox login): {dl_url}")

    # Return as Image if it's an image type so the agent can see it
    image_exts  = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    image_types = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}
    is_image    = (ftype.lower() in image_types or
                   any(name.lower().endswith(ext) for ext in image_exts))

    if is_image:
        fmt = (ftype.split("/")[-1] if "/" in ftype else
               next((ext.lstrip(".") for ext in image_exts if name.lower().endswith(ext)), "png"))
        fmt = fmt.replace("jpeg", "jpg")
        return Image(data=dl.content, format=fmt)

    return (f"Downloaded '{name}' (id={attachment_id})\n"
            f"Type : {ftype or 'unknown'}\n"
            f"Size : {_fmt_size(size)}\n"
            f"Note : Non-image file - cannot be displayed inline.\n"
            f"URL  : {dl_url}")


@mcp.tool()
def list_statuses() -> str:
    """List all ticket statuses with IDs. Use IDs with change_ticket_status()."""
    r = requests.get(f"{BASE_URL}/statuses/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"
    lines = ["Available Statuses:", ""]
    for s in r.json():
        lines.append(f"  id={s['id']:<4}  behavior={s.get('behavior','?'):<12}  name={s['name']}")
    return "\n".join(lines)


@mcp.tool()
def list_categories() -> str:
    """List all ticket categories with IDs. Use with list_tickets(category_id=...)."""
    r = requests.get(f"{BASE_URL}/categories/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"
    lines = ["Available Categories:", ""]
    for c in r.json():
        lines.append(f"  id={c['id']:<4}  name={c.get('name','?')}")
    return "\n".join(lines)


@mcp.tool()
def list_staff() -> str:
    """List all staff/agents with IDs. Staff ID required for posting updates."""
    r = requests.get(f"{BASE_URL}/staff/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"
    lines = ["Staff / Agents:", ""]
    for s in r.json():
        active = "active" if s.get("active") else "inactive"
        lines.append(f"  id={s['id']:<4}  {active:<8}  {s.get('name','?')}  <{s.get('email','?')}>")
    return "\n".join(lines)


# ===========================================================================
# WRITE TOOLS
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

    IMPORTANT: Show the exact message to the user and get approval before
    calling. Replies are sent immediately and cannot be unsent.

    Args:
        ticket_id:      Numeric ticket ID.
        message:        Reply or note body (plain text).
        staff_id:       Staff ID posting the update (from list_staff).
        is_private:     True = private internal note. False = public reply.
        status_id:      Optional status ID to change at the same time.
        notify_contact: Email the contact? Ignored for private notes.
    """
    if is_private:
        endpoint = f"{BASE_URL}/ticket/{ticket_id}/staff_pvtnote/"
        payload  = {"staff": staff_id, "plaintext": message}
    else:
        endpoint = f"{BASE_URL}/ticket/{ticket_id}/staff_update/"
        payload  = {"staff": staff_id, "plaintext": message, "update_customer": notify_contact}

    if status_id is not None:
        payload["status"] = status_id

    r = requests.post(endpoint, auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        kind   = "Private note" if is_private else "Reply"
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
    Create a new support ticket. IMPORTANT: Confirm all details first.

    Args:
        subject:       Ticket subject line.
        message:       Opening message (plain text).
        contact_name:  Contact's name.
        contact_email: Contact's email address.
        category_id:   Category ID (from list_categories).
        priority_id:   Optional priority ID.
        assignee_id:   Optional staff ID to assign (from list_staff).
    """
    payload = {"subject": subject, "text": message, "name": contact_name,
               "email": contact_email, "category": category_id}
    if priority_id is not None:
        payload["priority"] = priority_id
    if assignee_id is not None:
        payload["assignee"] = assignee_id

    r = requests.post(f"{BASE_URL}/tickets/", auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        c = r.json()
        return f"Ticket created: #{c.get('id')}  {c.get('display_id')}  - {c.get('subject')}"
    return f"Error {r.status_code}: {r.text}"


@mcp.tool()
def suggest_ticket_rename(ticket_id: int, suggested_subject: str, staff_id: int) -> str:
    """
    Post a private note suggesting a better ticket title.

    The HappyFox v1.1 API cannot rename ticket subjects directly (confirmed
    hard API limitation). This posts a private note so an agent can apply
    the rename manually in the UI in two clicks.

    Args:
        ticket_id:         Numeric ticket ID.
        suggested_subject: The recommended new title.
        staff_id:          Staff ID posting the note (from list_staff).
    """
    note = (f"[AI TITLE SUGGESTION]\n"
            f"Suggested title: {suggested_subject}\n\n"
            f"The original subject was unclear. Please rename manually in HappyFox UI.")
    r = requests.post(f"{BASE_URL}/ticket/{ticket_id}/staff_pvtnote/",
                      auth=_auth(),
                      json={"staff": staff_id, "plaintext": note})
    if r.status_code in (200, 201):
        return (f"Private note posted to ticket #{ticket_id} suggesting title: \"{suggested_subject}\"\n"
                f"An agent will need to apply the rename manually via the UI.")
    return f"Error {r.status_code}: {r.text}"


@mcp.tool()
def change_ticket_status(ticket_id: int, status_id: int, staff_id: int) -> str:
    """
    Change the status of a ticket. Use list_statuses() to find IDs.

    Args:
        ticket_id: Numeric ticket ID.
        status_id: New status ID (from list_statuses).
        staff_id:  Staff ID making the change (from list_staff).
    """
    r = requests.post(f"{BASE_URL}/ticket/{ticket_id}/staff_update/",
                      auth=_auth(),
                      json={"staff": staff_id, "status": status_id})
    if r.status_code in (200, 201):
        return f"Ticket #{ticket_id} status changed to id={status_id}."
    return f"Error {r.status_code}: {r.text}"


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    mcp.run(transport=_transport)

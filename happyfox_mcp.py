import os
import re
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

mcp = FastMCP(
    "HappyFox",
    host=_host,
    port=_port,
    # Serve at root so clients can connect to http://host:8000/
    # without needing to know the /mcp subpath FastMCP defaults to.
    streamable_http_path="/",
    sse_path="/sse",
)

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

def _strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text).strip()

@mcp.tool()
def get_ticket_attachments(ticket_id: int) -> str:
    """
    Download and display attachments from a ticket.

    Fetches all attachments associated with a ticket, including images,
    documents, and other files. For image attachments, the content is
    returned inline so it can be viewed directly. For non-image files,
    download URLs are provided.

    IMPORTANT: This tool downloads actual file data from HappyFox servers.
    Large files or many attachments may take time to fetch.

    Args:
        ticket_id: Numeric ticket ID (from list_tickets).
    """
    # First try to get attachment metadata from the ticket endpoint
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r = requests.get(url, auth=_auth())
    
    if r.status_code != 200:
        return f"Error {r.status_code}: Failed to fetch ticket data\n{r.text}"
    
    t = r.json()
    attachments = t.get("attachments", [])
    
    if not attachments:
        return f"Ticket #{ticket_id} has no attachments."
    
    lines = [f"Attachments for Ticket #{ticket_id}:", ""]
    
    for att in attachments:
        filename = att.get("filename", "unknown")
        size_kb = att.get("size", 0) / 1024 if att.get("size") else 0
        mime_type = att.get("mime_type", "")
        
        # Check if this is an image attachment
        is_image = any(ext in mime_type.lower() for ext in ["image/", "png", "jpg", "jpeg"])
        
        lines.append(f"File: {filename}")
        lines.append(f"  Size: {size_kb:.1f} KB")
        lines.append(f"  Type: {mime_type or 'unknown'}")
        
        # Try to get download URL from attachment metadata
        download_url = None
        
        # HappyFox API sometimes includes direct URLs in attachments
        if "url" in att:
            download_url = att["url"]
        elif "download_url" in att:
            download_url = att["download_url"]
        
        # Try to construct URL based on HappyFox patterns
        if not download_url and att.get("id"):
            # Pattern 1: /api/1.1/attachment/{id}
            download_url = f"{BASE_URL}/attachment/{att['id']}"
        
        if download_url:
            lines.append(f"  Download URL: {download_url}")
            
            # For images, try to fetch and display inline
            if is_image:
                try:
                    img_response = requests.get(
                        download_url, 
                        auth=_auth(),
                        headers={"Accept": "image/*"}
                    )
                    
                    if img_response.status_code == 200:
                        # Convert to base64 for inline display
                        import base64
                        b64_data = base64.b64encode(img_response.content).decode('utf-8')
                        lines.append(f"  Image (base64): data:{mime_type};base64,{b64_data[:50]}...")
                        lines.append("  [Full image data truncated - use download URL for complete file]")
                    else:
                        lines.append(f"  Image fetch failed: HTTP {img_response.status_code}")
                except Exception as e:
                    lines.append(f"  Error fetching image: {str(e)}")
        else:
            lines.append("  Download URL: Not available (try HappyFox web UI)")
        
        lines.append("")
    
    return "\n".join(lines)


@mcp.tool()
def download_attachment(attachment_id: int, output_path: str = None) -> str:
    """
    Download a specific attachment from HappyFox and save it locally.

    Returns the local file path where the attachment was saved. If no
    output_path is provided, saves to /mnt/uploads/ with the original filename.

    Args:
        attachment_id: Numeric attachment ID (from get_ticket_attachments).
        output_path: Optional custom path to save the file. Defaults to /mnt/uploads/.
    """
    # Get attachment metadata first
    url = f"{BASE_URL}/attachment/{attachment_id}"
    r = requests.get(url, auth=_auth())
    
    if r.status_code != 200:
        return f"Error {r.status_code}: Failed to fetch attachment metadata\n{r.text}"
    
    att = r.json()
    filename = att.get("filename", "attachment")
    mime_type = att.get("mime_type", "application/octet-stream")
    
    # Get download URL
    download_url = None
    if "url" in att:
        download_url = att["url"]
    elif "download_url" in att:
        download_url = att["download_url"]
    else:
        return f"No download URL available for attachment {attachment_id}"
    
    # Fetch the actual file content
    r = requests.get(download_url, auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: Failed to download attachment\n{r.text}"
    
    # Determine output path
    if not output_path:
        import os
        os.makedirs("/mnt/uploads", exist_ok=True)
        output_path = f"/mnt/uploads/{filename}"
    
    # Save file
    with open(output_path, "wb") as f:
        f.write(r.content)
    
    size_kb = len(r.content) / 1024
    
    return (
        f"Attachment downloaded successfully!\n"
        f"Filename: {filename}\n"
        f"Size: {size_kb:.1f} KB\n"
        f"MIME Type: {mime_type}\n"
        f"Saved to: {output_path}"
    )


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
    Return a compact, agent-friendly summary of tickets — titles and key
    metadata ONLY. No message bodies are included so this never blows out
    a context window.

    Use get_ticket_details() or get_ticket_messages() to drill into a
    specific ticket once you have its ID.

    Args:
        status:      '_pending' (default), '_all', '_completed', or a numeric
                     status ID string. Use list_statuses() to see valid values.
        query:       Optional HappyFox search string (same syntax as the UI).
        page:        Page number (1-based).
        size:        Tickets per page (1-50, default 20).
        category_id: Optional category ID to filter results. Use
                     list_categories() to find valid IDs.
    """
    url    = f"{BASE_URL}/tickets/"
    params = {
        "status": status,
        "q":      query,
        "page":   page,
        "size":   min(size, 50),
    }
    # HappyFox accepts ?category=<id> to filter by a single category.
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

    # Header line — include category filter hint if one was applied
    header = (
        f"Tickets (page {page}/{page_info.get('page_count', '?')}, "
        f"total: {page_info.get('count', '?')})"
    )
    if category_id is not None:
        header += f"  [category id={category_id}]"

    lines = [
        header,
        "",
        f"{'ID':<8} {'Display ID':<14} {'Status':<14} {'Priority':<10} "
        f"{'Assignee':<20} {'Subject'}",
        "-" * 100,
    ]

    for t in tickets:
        tid        = t.get("id", "")
        display_id = t.get("display_id", "")
        subject    = t.get("subject", "(no subject)")
        status_nm  = (
            t.get("status", {}).get("name", "?")
            if isinstance(t.get("status"), dict)
            else str(t.get("status", ""))
        )
        priority = (
            t.get("priority", {}).get("name", "?")
            if isinstance(t.get("priority"), dict)
            else ""
        )
        assignee = "Unassigned"
        if isinstance(t.get("assigned_to"), dict):
            assignee = t["assigned_to"].get("name", "Unassigned")

        short_subject = subject if len(subject) <= 55 else subject[:52] + "..."

        lines.append(
            f"{str(tid):<8} {display_id:<14} {status_nm:<14} {priority:<10} "
            f"{assignee:<20} {short_subject}"
        )

    lines += [
        "",
        "Use get_ticket_details(ticket_id) to read a specific ticket.",
    ]
    if page_info.get("page_count", 1) > page:
        lines.append(f"Use list_tickets(page={page + 1}) to see the next page.")

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
    url = f"{BASE_URL}/ticket/{ticket_id}/"
    r   = requests.get(url, auth=_auth())
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
        f"Subject    : {t.get('subject', '(no subject)')}",
        f"Status     : {t.get('status', {}).get('name', '?')}  (id={t.get('status', {}).get('id', '?')})",
        f"Priority   : {t.get('priority', {}).get('name', '?')}  (id={t.get('priority', {}).get('id', '?')})",
        f"Category   : {t.get('category', {}).get('name', '?')}  (id={t.get('category', {}).get('id', '?')})",
        f"Assignee   : {assignee}",
        f"Contact    : {t.get('user', {}).get('name', '?')} <{t.get('user', {}).get('email', '?')}>",
        f"Created    : {t.get('created_at', '?')}",
        f"Updated    : {t.get('last_updated_at', '?')}",
        f"Messages   : {t.get('messages_count', 0)}  (use get_ticket_messages to read them)",
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
    Return the conversation thread for a ticket — the most recent N messages.

    Each message body is returned in full so you can draft replies with full
    context. Keep max_messages small to avoid filling the context window.

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

    lines = [
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
    change_ticket_status() or add_ticket_update().
    """
    r = requests.get(f"{BASE_URL}/statuses/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    statuses = r.json()
    lines    = ["Available Statuses:", ""]
    for s in statuses:
        lines.append(
            f"  id={s['id']:<4}  behavior={s.get('behavior', '?'):<12}  name={s['name']}"
        )
    return "\n".join(lines)


@mcp.tool()
def list_categories() -> str:
    """
    List all ticket categories configured in HappyFox with their IDs.

    Use the category ID with list_tickets(category_id=...) to filter the
    ticket queue to a specific category, or with create_ticket() to file
    a ticket under the right category.
    """
    r = requests.get(f"{BASE_URL}/categories/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    categories = r.json()
    lines      = ["Available Categories:", ""]
    for c in categories:
        lines.append(
            f"  id={c['id']:<4}  name={c.get('name', '?')}"
        )
    return "\n".join(lines)


@mcp.tool()
def list_staff() -> str:
    """
    List all staff/agents with their IDs.

    The staff ID is required when posting updates, private notes, or
    changing ticket status.
    """
    r = requests.get(f"{BASE_URL}/staff/", auth=_auth())
    if r.status_code != 200:
        return f"Error {r.status_code}: {r.text}"

    staff = r.json()
    lines = ["Staff / Agents:", ""]
    for s in staff:
        active = "active" if s.get("active") else "inactive"
        lines.append(
            f"  id={s['id']:<4}  {active:<8}  {s.get('name', '?')}  <{s.get('email', '?')}>"
        )
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
    explicit approval before calling this tool. Replies are sent immediately
    and cannot be unsent.

    Args:
        ticket_id:      Numeric ticket ID.
        message:        The reply or note body (plain text).
        staff_id:       ID of the staff member posting the update (from list_staff).
        is_private:     If True, posts as a private internal note (not sent to
                        the contact). Default False (public reply).
        status_id:      Optional status ID to set at the same time (e.g. to
                        close the ticket). Use list_statuses() to find IDs.
        notify_contact: Whether to email the contact. Ignored for private notes.
    """
    if is_private:
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
    Create a new support ticket.

    IMPORTANT: Confirm all details with the user before calling this.

    Args:
        subject:       Ticket subject line.
        message:       Opening message body (plain text).
        contact_name:  Name of the contact the ticket is for.
        contact_email: Email address of the contact.
        category_id:   HappyFox category ID (use list_categories() to find IDs).
        priority_id:   Optional priority ID.
        assignee_id:   Optional staff ID to assign immediately (from list_staff).
    """
    url     = f"{BASE_URL}/tickets/"
    payload = {
        "subject":  subject,
        "text":     message,
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
def suggest_ticket_rename(ticket_id: int, suggested_subject: str, staff_id: int) -> str:
    """
    Flag a ticket for renaming by posting a private internal note with the
    suggested new title.

    The HappyFox v1.1 API does not expose ticket subject editing — the
    'subject' field on staff_update only controls the outgoing email reply
    subject line, not the ticket title, and returns a 400 error when used
    alone. This is a confirmed hard limitation of the API (the edit_subject
    permission exists in HappyFox but is only accessible through the UI).

    This tool posts a clearly-formatted private note instead. The note is
    visible to agents when they open the ticket, so they can apply the rename
    manually in two clicks. The note is never shown to the contact.

    IMPORTANT: Confirm the suggested title with the user before calling this.

    Args:
        ticket_id:         Numeric ticket ID.
        suggested_subject: The recommended new subject / title.
        staff_id:          ID of the staff member posting the note (from list_staff).
    """
    note = (
        f"[AI TITLE SUGGESTION]\n"
        f"Suggested title: {suggested_subject}\n\n"
        f"The original subject was unclear. Please rename this ticket manually "
        f"in HappyFox if the suggested title is accurate."
    )
    url     = f"{BASE_URL}/ticket/{ticket_id}/staff_pvtnote/"
    payload = {
        "staff":     staff_id,
        "plaintext": note,
    }
    r = requests.post(url, auth=_auth(), json=payload)
    if r.status_code in (200, 201):
        return (
            f"Private note posted to ticket #{ticket_id} with suggested title: "
            f"\"{suggested_subject}\"\n"
            f"Note: The HappyFox API does not support renaming ticket titles directly. "
            f"An agent will need to apply the rename manually via the UI."
        )
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
    # .run() only accepts 'transport' — passing host/port here raises TypeError.
    mcp.run(transport=_transport)

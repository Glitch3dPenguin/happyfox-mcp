import os
import re
import logging
from datetime import datetime
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP, Image

# ---------------------------------------------------------------------------
# Logging setup — suppress noisy ClientDisconnect / Starlette warnings so the
# server logs stay clean for operators.
# ---------------------------------------------------------------------------
logging.getLogger("mcp.server.streamable_http").setLevel(logging.INFO)
logging.getLogger("starlette.requests").setLevel(logging.WARNING)

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

_TIMEOUT = 30  # every HappyFox call MUST use this — tools must never hang

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

def _config_problem() -> str:
    missing = [
        name
        for name, value in (
            ("HAPPYFOX_DOMAIN", HAPPYFOX_DOMAIN),
            ("HAPPYFOX_API_KEY", API_KEY),
            ("HAPPYFOX_AUTH_CODE", AUTH_CODE),
        )
        if not value
    ]
    if not missing:
        return ""
    return ("Missing required environment variable(s): " + ", ".join(missing)
            + " — set them and restart the server.")

def _error(status: int, body: str) -> str:
    hints = {
        401: " — check HAPPYFOX_API_KEY and HAPPYFOX_AUTH_CODE",
        403: " — this API key's role lacks permission for that operation",
        404: " — not found; check the ID with a list_* tool",
    }
    return f"Error {status}: {_truncate(body, 300)}{hints.get(status, '')}"

def _api_get(url: str, params: dict = None):
    """GET a HappyFox endpoint. Returns (True, data) or (False, error_string).

    Centralizes the mandatory 30s timeout and defensive JSON parsing so no
    tool can hang forever or crash on a non-JSON error page.
    """
    problem = _config_problem()
    if problem:
        return False, problem
    r = requests.get(url, auth=_auth(), params=params, timeout=_TIMEOUT)
    if r.status_code != 200:
        return False, _error(r.status_code, r.text)
    try:
        return True, r.json()
    except ValueError:
        return False, f"Error: expected JSON from {url} but got a non-JSON response."

def _api_post(url: str, payload: dict):
    """POST a HappyFox endpoint. Returns (True, data) or (False, error_string)."""
    problem = _config_problem()
    if problem:
        return False, problem
    r = requests.post(url, auth=_auth(), json=payload, timeout=_TIMEOUT)
    if r.status_code not in (200, 201):
        return False, _error(r.status_code, r.text)
    try:
        return True, r.json()
    except ValueError:
        return True, None

def _valid_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def _q_clause(field: str, value: str) -> str:
    """Build one advanced-search clause like assignee:none or contact:"a b"."""
    value = value.strip()
    if not value:
        return ""
    if any(ch in value for ch in ' ,"'):
        value = f'"{value.replace(chr(34), "")}"'
    return f"{field}:{value}"

def _q_list(field: str, csv: str) -> str:
    """Build a multi-value clause like priority:"High","Medium"."""
    parts = [p.strip().replace('"', "") for p in csv.split(",") if p.strip()]
    if not parts:
        return ""
    return field + ":" + ",".join(f'"{p}"' for p in parts)

def _cf_lines(fields, label: str) -> list:
    """Format non-empty custom field values as 'name=value' pairs."""
    parts = []
    for f in fields or []:
        if not isinstance(f, dict):
            continue
        v = f.get("value")
        if v in (None, "", []):
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        parts.append(f"{f.get('name', '?')}={v}")
    if not parts:
        return []
    return [f"{label}: " + "; ".join(parts)]

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
def check_connection() -> str:
    """
    Verify that credentials and connectivity work, with a quick account
    summary. Run this first when debugging a new setup.
    """
    ok, staff = _api_get(f"{BASE_URL}/staff/")
    if not ok:
        return f"Connection FAILED: {staff}"
    if not isinstance(staff, list):
        return f"Connection OK, but /staff/ returned an unexpected response: {_truncate(str(staff), 200)}"
    active = sum(1 for s in staff if isinstance(s, dict) and s.get("active"))
    return (f"Connected to https://{HAPPYFOX_DOMAIN} — OK.\n"
            f"Staff: {len(staff)} total, {active} active.\n"
            f"Use list_staff() for IDs and list_statuses()/list_categories()/"
            f"list_priorities() to explore the account.")


@mcp.tool()
def list_tickets(
    status:      str = "_pending",
    query:       str = "",
    page:        int = 1,
    size:        int = 20,
    category_id: Optional[int] = None,
    assignee:    str = "",
    priority:    str = "",
    tag:         str = "",
    duedate:     str = "",
    contact:     str = "",
    unresponded: bool = False,
    breached:    bool = False,
    sort:        str = "",
) -> str:
    """
    Return a compact, agent-friendly summary of tickets - titles and key
    metadata ONLY. No message bodies included so this never blows out context.

    Use get_ticket_details() or get_ticket_messages() to drill into a ticket.
    Use get_ticket_attachments() to list files on a ticket.

    Args:
        status:      '_pending' (default), '_all', '_completed', or a numeric
                     status ID. Use list_statuses() to see valid values.
        query:       Free-form HappyFox search string (advanced filters).
        page:        Page number (1-based).
        size:        Tickets per page (1-50, default 20).
        category_id: Optional category ID to filter. Use list_categories() for IDs.
        assignee:    'none' (unassigned), 'any' (assigned), or a staff name/email
                     keyword (case-sensitive exact match). Use list_staff() for names.
        priority:    Comma-separated priority names, e.g. 'High,Medium'.
                     Use list_priorities() for valid names.
        tag:         Comma-separated tags (case-sensitive).
        duedate:     'today', 'yesterday', 'tomorrow', 'overdue', or 'next 7 days'.
        contact:     Comma-separated keywords matched against contact name,
                     email, or phone.
        unresponded: True = only tickets with no staff response yet.
        breached:    True = only tickets that breached at least one SLA.
        sort:        One of: due, prioritya, priorityd, created, createa,
                     updated, updatea, subjecta, subjectd, statusa, statusd,
                     assigneea, assigneed, ticketa, ticketd, categorya,
                     categoryd, clienta, clientd, last_modifieda, last_modifiedd,
                     unresponded.
    """
    page = max(1, page)
    size = max(1, min(size, 50))

    clauses = []
    if query.strip():
        clauses.append(query.strip())
    for clause in (
        _q_clause("assignee", assignee),
        _q_list("priority", priority),
        _q_list("tag", tag),
        _q_list("contact", contact),
    ):
        if clause:
            clauses.append(clause)
    if duedate.strip():
        dd = duedate.strip().lower().replace("-", " ")
        if dd not in ("today", "yesterday", "tomorrow", "overdue", "next 7 days"):
            return ("Invalid duedate. Allowed values: today, yesterday, tomorrow, "
                    "overdue, 'next 7 days'.")
        clauses.append(f"duedate:{dd}")
    if unresponded:
        clauses.append("unresponded:true")
    if breached:
        clauses.append("breached:true")

    params = {"status": status, "page": page, "size": size}
    if clauses:
        params["q"] = " ".join(clauses)
    if category_id is not None:
        params["category"] = category_id
    if sort.strip():
        params["sort"] = sort.strip()

    ok, data = _api_get(f"{BASE_URL}/tickets/", params=params)
    if not ok:
        return data

    page_info = data.get("page_info", {})
    tickets   = data.get("data", [])

    if not tickets:
        return "No tickets found matching those criteria."

    header = (f"Tickets (page {page}/{page_info.get('page_count', '?')}, "
              f"total: {page_info.get('count', '?')})")
    if category_id is not None:
        header += f"  [category id={category_id}]"
    if clauses:
        header += f"  [filter: {params['q']}]"

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
    ok, t = _api_get(f"{BASE_URL}/ticket/{ticket_id}/")
    if not ok:
        return t

    assignee = "Unassigned"
    if isinstance(t.get("assigned_to"), dict):
        assignee = t["assigned_to"].get("name", "Unassigned")

    # `or {}` guards against explicit nulls from the API (see get_ticket_messages).
    status   = t.get("status") or {}
    priority = t.get("priority") or {}
    category = t.get("category") or {}
    contact  = t.get("user") or {}

    attach_count = t.get("attachments_count", 0)
    attach_hint  = (f"{attach_count}  (call get_ticket_attachments to list + download)"
                    if attach_count > 0 else "0")

    time_spent = t.get("time_spent")
    pp         = contact.get("primary_phone")
    phone      = pp.get("number", "") if isinstance(pp, dict) else ""
    groups     = ", ".join(g.get("name", "?") for g in (contact.get("contact_groups") or [])
                           if isinstance(g, dict))

    lines = [
        "=" * 60,
        f"Ticket #{ticket_id}  {t.get('display_id', '')}",
        "=" * 60,
        f"Subject    : {t.get('subject', '(no subject)')}",
        f"Status     : {status.get('name', '?')}  (id={status.get('id', '?')})",
        f"Priority   : {priority.get('name', '?')}  (id={priority.get('id', '?')})",
        f"Category   : {category.get('name', '?')}  (id={category.get('id', '?')})",
        f"Assignee   : {assignee}",
        f"Contact    : {contact.get('name', '?')} <{contact.get('email', '?')}>",
        f"Due date   : {t.get('due_date') or '-'}",
        f"Tags       : {t.get('tags') or '-'}",
        f"SLA breaches: {t.get('sla_breaches', 0) or 0}   Unresponded: {'yes' if t.get('unresponded') else 'no'}",
        f"Source     : {t.get('source') or '-'}   Time spent: {time_spent if time_spent is not None else '-'} min",
        f"Last staff reply  : {t.get('last_staff_reply_at') or 'never'}",
        f"Last contact reply: {t.get('last_user_reply_at') or 'never'}",
        f"Created    : {t.get('created_at', '?')}",
        f"Updated    : {t.get('last_updated_at', '?')}",
        f"Messages   : {t.get('messages_count', 0)}  (call get_ticket_messages to read)",
        f"Attachments: {attach_hint}",
    ]
    if phone:
        lines.append(f"Contact phone: {phone}")
    if groups:
        lines.append(f"Contact groups: {groups}")
    if contact.get("tickets_count") is not None:
        lines.append(f"Contact tickets: {contact.get('tickets_count')} total, "
                     f"{contact.get('pending_tickets_count', 0)} pending")
    lines += _cf_lines(t.get("custom_fields"), "Ticket custom fields")
    lines += _cf_lines(contact.get("custom_fields"), "Contact custom fields")
    lines += [
        "",
        "--- Opening Message ---",
        _truncate(t.get("first_message") or "", max_chars=600),
    ]
    return "\n".join(lines)


@mcp.tool()
def get_ticket_messages(ticket_id: int, max_messages: int = 5, from_start: bool = False) -> str:
    """
    Return the conversation thread for a ticket - a window of N messages.

    By default returns the most recent N; with from_start=True returns the
    first N (useful to see how a long thread began).

    Attachment names are noted inline; use download_attachment() to fetch them.

    Args:
        ticket_id:    Numeric ticket ID.
        max_messages: How many messages to return (default 5).
        from_start:   True = start of the thread. False (default) = most recent.
    """
    max_messages = max(1, max_messages)
    ok, t = _api_get(f"{BASE_URL}/ticket/{ticket_id}/")
    if not ok:
        return t

    updates = t.get("updates", [])
    if not updates:
        return f"Ticket #{ticket_id} has no message updates yet."

    if from_start:
        window = updates[:max_messages]
        label  = f"First {len(window)} of {len(updates)}"
    else:
        window = updates[-max_messages:]
        label  = f"Last {len(window)} of {len(updates)}"

    lines = [
        f"{label} messages in ticket #{ticket_id} ({t.get('display_id', '')}): {t.get('subject', '')}",
        "",
    ]
    for i, upd in enumerate(window, 1):
        # NOTE: `or {}`, not a .get default - HappyFox returns explicit `null`
        # for e.g. image-only replies (message: null) or system updates
        # (by: null), and .get("key", {}) does NOT guard against null values.
        by     = upd.get("by") or {}
        author = f"{by.get('name', '?')} ({by.get('type', '?')})"
        ts     = upd.get("timestamp", "?")
        msg    = upd.get("message") or {}
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

    if from_start and len(window) < len(updates):
        lines.append(f"(Use get_ticket_messages({ticket_id}, max_messages={len(updates) - max_messages}, from_start=false) for the rest of the thread.)")
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
    ok, t = _api_get(f"{BASE_URL}/ticket/{ticket_id}/")
    if not ok:
        return t

    all_attachments = _collect_attachments(t)

    if not all_attachments:
        # Fallback: some accounts embed files inline as CID references in the
        # message HTML without structured attachment objects. Scan for them
        # and try to resolve each one via the CID endpoint.
        cids = re.findall(r"cid:([a-f0-9\-]+)", t.get("first_message") or "")
        for cid in cids:
            ok, c = _api_get(f"{BASE_URL}/attachment_by_cid/{cid}")
            if not ok or not isinstance(c, dict):
                continue
            all_attachments.append({
                "id":      c.get("id", cid),
                "name":    c.get("name") or c.get("filename", f"attachment_{cid[:8]}"),
                "type":    c.get("type") or c.get("mime_type", "unknown"),
                "size":    c.get("size", 0),
                "url":     c.get("url") or c.get("download_url", ""),
                "_source": "Inline CID reference",
            })

    if not all_attachments:
        return (f"Ticket #{ticket_id} ({t.get('display_id', '')}) has no attachments.\n"
                f"(attachments_count from API: {t.get('attachments_count', 0)} — "
                f"they may be inline CID references that could not be resolved.)")

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
        size  = _fmt_size(a.get("size") or 0)
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
    ok, t = _api_get(f"{BASE_URL}/ticket/{ticket_id}/")
    if not ok:
        return f"Error fetching ticket {ticket_id}: {t}"

    all_attachments = _collect_attachments(t)
    target = next((a for a in all_attachments if a.get("id") == attachment_id), None)

    if not target:
        return (f"Attachment id={attachment_id} not found on ticket #{ticket_id}. "
                f"Run get_ticket_attachments({ticket_id}) to see valid IDs.")

    name   = target.get("name", "file")
    ftype  = target.get("type") or target.get("content_type") or ""
    size   = target.get("size") or 0
    dl_url = target.get("url") or target.get("download_url") or ""

    if not dl_url:
        return (f"Attachment '{name}' (id={attachment_id}) has no download URL in the API response. "
                f"Size: {_fmt_size(size)}, Type: {ftype}")

    # Download — try with auth first, then without (pre-signed URLs don't need it).
    # NOTE: dl_url is an EXTERNAL pre-signed S3 URL, not a HappyFox API endpoint,
    # so it is fetched directly instead of via _api_get.
    dl = requests.get(dl_url, auth=_auth(), timeout=_TIMEOUT)
    if dl.status_code != 200:
        dl = requests.get(dl_url, timeout=_TIMEOUT)
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
    ok, data = _api_get(f"{BASE_URL}/statuses/")
    if not ok:
        return data
    lines = ["Available Statuses:", ""]
    for s in data:
        lines.append(f"  id={s['id']:<4}  behavior={s.get('behavior','?'):<12}  name={s['name']}")
    return "\n".join(lines)


@mcp.tool()
def list_categories() -> str:
    """List all ticket categories with IDs. Use with list_tickets(category_id=...)."""
    ok, data = _api_get(f"{BASE_URL}/categories/")
    if not ok:
        return data
    lines = ["Available Categories:", ""]
    for c in data:
        lines.append(f"  id={c['id']:<4}  name={c.get('name','?')}")
    return "\n".join(lines)


@mcp.tool()
def list_priorities() -> str:
    """
    List all ticket priorities configured in HappyFox with their IDs and names.

    Use the priority ID with change_ticket_priority() to escalate or
    de-escalate a ticket, or the names with list_tickets(priority=...).
    """
    ok, data = _api_get(f"{BASE_URL}/priorities/")
    if not ok:
        return data
    lines = ["Available Priorities:", ""]
    for p in data:
        lines.append(f"  id={p['id']:<4}  name={p.get('name', '?')}")
    return "\n".join(lines)


@mcp.tool()
def list_staff() -> str:
    """
    List all staff/agents with IDs. Staff ID required for posting updates and
    making ticket changes. Names/emails also work in list_tickets(assignee=...).
    """
    ok, data = _api_get(f"{BASE_URL}/staff/")
    if not ok:
        return data
    lines = ["Staff / Agents:", ""]
    for s in data:
        active = "active" if s.get("active") else "inactive"
        lines.append(f"  id={s['id']:<4}  {active:<8}  {s.get('name','?')}  <{s.get('email','?')}>")
    return "\n".join(lines)


@mcp.tool()
def list_ticket_custom_fields() -> str:
    """
    List all ticket custom fields with IDs, types, and choice options.

    Use the IDs with update_ticket_custom_fields() (as 't-cf-<id>'). Ticket
    detail output shows each ticket's current values.
    """
    ok, data = _api_get(f"{BASE_URL}/ticket_custom_fields/")
    if not ok:
        return data
    if not data:
        return "This account has no ticket custom fields."
    lines = ["Ticket custom fields:", ""]
    for f in data:
        if f.get("required"):
            req = "required"
        elif f.get("compulsory_on_completed"):
            req = "compulsory-on-close"
        else:
            req = "optional"
        choices = ""
        if f.get("choices"):
            choices = "  choices: " + ", ".join(
                f"{c.get('text')} (id={c.get('id')})" for c in f["choices"] if isinstance(c, dict)
            )
        lines.append(f"  id={f.get('id', '?'):<4}  {str(f.get('type', '?')):<12}  {req:<18}  {f.get('name', '?')}{choices}")
    lines += [
        "",
        "Set values: update_ticket_custom_fields(ticket_id, staff_id, {'t-cf-<id>': value})",
        "Contact custom fields appear as 'c-cf-<id>' (see ticket details for contact field values).",
    ]
    return "\n".join(lines)


@mcp.tool()
def list_contacts(query: str = "", page: int = 1, size: int = 20) -> str:
    """
    List contacts (customers) in the account.

    Args:
        query: Optional search on name, email, or phone. Format 'field:value',
               e.g. 'name:adam' or 'email:adam@example.com' or
               'phone:11231231234'. Combine fields with spaces.
        page:  Page number (1-based).
        size:  Contacts per page (1-50, default 20).
    """
    page = max(1, page)
    size = max(1, min(size, 50))
    params = {"page": page, "size": size}
    if query.strip():
        params["q"] = query.strip()

    ok, data = _api_get(f"{BASE_URL}/users/", params=params)
    if not ok:
        return data

    page_info = data.get("page_info", {}) if isinstance(data, dict) else {}
    contacts  = data.get("data", []) if isinstance(data, dict) else []

    if not contacts:
        return "No contacts found matching those criteria."

    lines = [
        f"Contacts (page {page}/{page_info.get('page_count', '?')}, total: {page_info.get('count', '?')})",
        "",
        f"{'ID':<8} {'Name':<28} {'Email':<32} {'Pending/Total':<16} Phone",
        "-" * 100,
    ]
    for c in contacts:
        name  = c.get("name", "(no name)")
        email = c.get("email", "")
        pp    = c.get("primary_phone")
        phone = pp.get("number", "") if isinstance(pp, dict) else ""
        pc    = c.get("pending_tickets_count", 0) or 0
        tc    = c.get("tickets_count", 0) or 0
        lines.append(f"{str(c.get('id', '')):<8} {name[:28]:<28} {email[:32]:<32} {f'{pc}/{tc}':<16} {phone}")

    lines += ["", "Use get_contact(id-or-email) for full detail (groups, custom fields, all phones)."]
    if page_info.get("page_count", 1) > page:
        lines.append(f"Use list_contacts(page={page + 1}) for the next page.")
    return "\n".join(lines)


@mcp.tool()
def get_contact(identifier: str) -> str:
    """
    Full detail for ONE contact: phones, contact groups, ticket counts, and
    custom field values.

    Args:
        identifier: Numeric contact ID (from list_contacts) or email address.
    """
    ok, c = _api_get(f"{BASE_URL}/user/{identifier}/")
    if not ok:
        return f"Error looking up contact '{identifier}': {c}"

    phones = []
    for p in c.get("phones") or []:
        if isinstance(p, dict) and p.get("number"):
            phones.append(f"{p.get('number')} ({p.get('type', '?')})")
    groups = ", ".join(g.get("name", "?") for g in (c.get("contact_groups") or [])
                       if isinstance(g, dict))

    lines = [
        "=" * 60,
        f"Contact: {c.get('name', '?')}  (id={c.get('id', '?')})",
        "=" * 60,
        f"Email  : {c.get('email', '?')}",
        f"Phones : {', '.join(phones) or '-'}",
        f"Groups : {groups or '-'}",
        f"Tickets: {c.get('tickets_count', 0)} total, {c.get('pending_tickets_count', 0)} pending",
        f"Created: {c.get('created_at') or '-'}   Updated: {c.get('updated_at') or '-'}",
    ]
    lines += _cf_lines(c.get("custom_fields"), "Custom fields")
    lines += [
        "",
        f"To see their tickets: list_tickets(query='contact:{c.get('email', '')}', status='_all')",
    ]
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
    status_id:      Optional[int] = None,
    notify_contact: bool = True,
    cc:             str = "",
    bcc:            str = "",
    send_survey:    bool = False,
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
        cc:             Comma-separated CC emails (public replies only).
        bcc:            Comma-separated BCC emails (public replies only).
        send_survey:    Launch a satisfaction survey with the reply (public
                        replies only, typically when closing the ticket).
    """
    if is_private:
        endpoint = f"{BASE_URL}/ticket/{ticket_id}/staff_pvtnote/"
        payload  = {"staff": staff_id, "plaintext": message}
    else:
        endpoint = f"{BASE_URL}/ticket/{ticket_id}/staff_update/"
        payload  = {"staff": staff_id, "plaintext": message, "update_customer": notify_contact}
        if cc.strip():
            payload["cc"] = cc.strip()
        if bcc.strip():
            payload["bcc"] = bcc.strip()
        if send_survey:
            payload["send_survey"] = True

    if status_id is not None:
        payload["status"] = status_id

    ok, data = _api_post(endpoint, payload)
    if not ok:
        return data
    kind   = "Private note" if is_private else "Reply"
    result = f"{kind} posted successfully to ticket #{ticket_id}."
    if status_id is not None:
        result += f"  Status changed to id={status_id}."
    return result


@mcp.tool()
def create_ticket(
    subject:       str,
    message:       str,
    contact_name:  str,
    contact_email: str,
    category_id:   int,
    priority_id:   Optional[int] = None,
    assignee_id:   Optional[int] = None,
    phone:         str = "",
    tags:          str = "",
    due_date:      str = "",
    cc:            str = "",
) -> str:
    """
    Create a new support ticket. IMPORTANT: Confirm all details first.

    Args:
        subject:       Ticket subject line.
        message:       Opening message (plain text).
        contact_name:  Contact's name.
        contact_email: Contact's email address.
        category_id:   Category ID (from list_categories).
        priority_id:   Optional priority ID (from list_priorities).
        assignee_id:   Optional staff ID to assign (from list_staff).
        phone:         Optional contact phone number.
        tags:          Optional comma-separated tags.
        due_date:      Optional due date (yyyy-mm-dd).
        cc:            Optional comma-separated CC email addresses.
    """
    if due_date.strip() and not _valid_date(due_date.strip()):
        return "Invalid due_date. Use format yyyy-mm-dd (e.g. 2026-09-15)."

    payload = {"subject": subject, "text": message, "name": contact_name,
               "email": contact_email, "category": category_id}
    if priority_id is not None:
        payload["priority"] = priority_id
    if assignee_id is not None:
        payload["assignee"] = assignee_id
    if phone.strip():
        payload["phone"] = phone.strip()
    if tags.strip():
        payload["tags"] = tags.strip()
    if due_date.strip():
        payload["due_date"] = due_date.strip()
    if cc.strip():
        payload["cc"] = cc.strip()

    ok, c = _api_post(f"{BASE_URL}/tickets/", payload)
    if not ok:
        return c
    if isinstance(c, dict) and c.get("id") is not None:
        return f"Ticket created: #{c.get('id')}  {c.get('display_id', '')}  - {c.get('subject', '')}"
    return "Ticket created successfully."


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
    ok, data = _api_post(f"{BASE_URL}/ticket/{ticket_id}/staff_pvtnote/",
                         {"staff": staff_id, "plaintext": note})
    if not ok:
        return data
    return (f"Private note posted to ticket #{ticket_id} suggesting title: \"{suggested_subject}\"\n"
            f"An agent will need to apply the rename manually via the UI.")


@mcp.tool()
def change_ticket_status(ticket_id: int, status_id: int, staff_id: int) -> str:
    """
    Change the status of a ticket. Use list_statuses() to find IDs.

    Args:
        ticket_id: Numeric ticket ID.
        status_id: New status ID (from list_statuses).
        staff_id:  Staff ID making the change (from list_staff).
    """
    ok, data = _api_post(f"{BASE_URL}/ticket/{ticket_id}/staff_update/",
                         {"staff": staff_id, "status": status_id})
    if not ok:
        return data
    return f"Ticket #{ticket_id} status changed to id={status_id}."


@mcp.tool()
def assign_ticket(ticket_id: int, assignee_staff_id: int, staff_id: int) -> str:
    """
    Assign (or reassign) a ticket to a specific staff member.

    Use list_staff() to find valid staff IDs.

    Args:
        ticket_id:         Numeric ticket ID.
        assignee_staff_id: ID of the staff member to assign the ticket to.
        staff_id:          ID of the staff member making the change (can be
                           the same as assignee_staff_id for self-assignment).
    """
    ok, data = _api_post(
        f"{BASE_URL}/ticket/{ticket_id}/staff_update/",
        {"staff": staff_id, "assigned_to": assignee_staff_id},
    )
    if not ok:
        return data
    return f"Ticket #{ticket_id} assigned to staff id={assignee_staff_id}."


@mcp.tool()
def change_ticket_priority(ticket_id: int, priority_id: int, staff_id: int) -> str:
    """
    Change the priority of a ticket (e.g. escalate to Urgent or de-escalate).

    Use list_priorities() to find valid priority IDs.

    Args:
        ticket_id:   Numeric ticket ID.
        priority_id: ID of the new priority (from list_priorities).
        staff_id:    Staff ID making the change (from list_staff).
    """
    ok, data = _api_post(
        f"{BASE_URL}/ticket/{ticket_id}/staff_update/",
        {"staff": staff_id, "priority": priority_id},
    )
    if not ok:
        return data
    return f"Ticket #{ticket_id} priority changed to id={priority_id}."


@mcp.tool()
def change_ticket_category(ticket_id: int, category_id: int, staff_id: int) -> str:
    """
    Move a ticket into a different category.

    Use list_categories() to find valid category IDs.

    Args:
        ticket_id:   Numeric ticket ID.
        category_id: ID of the new category (from list_categories).
        staff_id:    Staff ID making the change (from list_staff).
    """
    ok, data = _api_post(
        f"{BASE_URL}/ticket/{ticket_id}/staff_update/",
        {"staff": staff_id, "category": category_id},
    )
    if not ok:
        return data
    return f"Ticket #{ticket_id} moved to category id={category_id}."


@mcp.tool()
def update_ticket_tags(ticket_id: int, staff_id: int, add: str = "", remove: str = "") -> str:
    """
    Add and/or remove tags on a ticket.

    IMPORTANT: Posts immediately with no undo. Confirm with the user first.

    Args:
        ticket_id: Numeric ticket ID.
        staff_id:  Staff ID making the change (from list_staff).
        add:       Comma-separated tags to add, e.g. 'billing,urgent'.
        remove:    Comma-separated tags to remove, e.g. 'stale'.
    """
    if not add.strip() and not remove.strip():
        return "Nothing to do - provide add and/or remove tags."
    payload = {"staff_id": staff_id}
    if add.strip():
        payload["add"] = add.strip()
    if remove.strip():
        payload["remove"] = remove.strip()

    ok, data = _api_post(f"{BASE_URL}/ticket/{ticket_id}/update_tags/", payload)
    if not ok:
        return data
    return (f"Tags updated on ticket #{ticket_id}: "
            f"added '{add.strip() or '-'}', removed '{remove.strip() or '-'}'.")


@mcp.tool()
def set_ticket_due_date(ticket_id: int, due_date: str, staff_id: int) -> str:
    """
    Set the due date on a ticket. Pass an empty string to clear it.

    IMPORTANT: Posts immediately with no undo. Confirm with the user first.

    Args:
        ticket_id: Numeric ticket ID.
        due_date:  Due date in yyyy-mm-dd format (e.g. 2026-09-15), or empty to clear.
        staff_id:  Staff ID making the change (from list_staff).
    """
    dd = due_date.strip()
    if dd and not _valid_date(dd):
        return "Invalid due_date. Use format yyyy-mm-dd (e.g. 2026-09-15), or an empty string to clear."

    ok, data = _api_post(
        f"{BASE_URL}/ticket/{ticket_id}/staff_update/",
        {"staff": staff_id, "due_date": dd or None},
    )
    if not ok:
        return data
    return f"Ticket #{ticket_id} due date {'set to ' + dd if dd else 'cleared'}."


@mcp.tool()
def update_ticket_custom_fields(ticket_id: int, staff_id: int, fields: dict) -> str:
    """
    Set custom field values on a ticket.

    Keys must be 't-cf-<id>' (ticket fields) or 'c-cf-<id>' (contact fields),
    where <id> comes from list_ticket_custom_fields() or the ticket details
    output. Values: strings, numbers, date strings (yyyy-mm-dd), choice option
    IDs, or lists of option IDs for multi-choice fields.

    IMPORTANT: Posts immediately with no undo. Confirm with the user first.

    Args:
        ticket_id: Numeric ticket ID.
        staff_id:  Staff ID making the change (from list_staff).
        fields:    Map of custom-field key to value, e.g. {"t-cf-3": [1, 2]}.
    """
    if not fields:
        return "Nothing to do - provide at least one field key/value."
    payload = {"staff": staff_id}
    for key, value in fields.items():
        if not isinstance(key, str) or not key.startswith(("t-cf-", "c-cf-")):
            return (f"Invalid field key '{key}'. Use 't-cf-<id>' or 'c-cf-<id>' "
                    f"(see list_ticket_custom_fields for valid IDs).")
        payload[key] = value

    ok, data = _api_post(f"{BASE_URL}/ticket/{ticket_id}/update_custom_fields/", payload)
    if not ok:
        return data
    return f"Custom fields updated on ticket #{ticket_id}: {', '.join(fields.keys())}."


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    mcp.run(transport=_transport)

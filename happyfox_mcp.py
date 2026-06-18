import os
import requests
from mcp.server.fastmcp import FastMCP
from typing import List, Optional

# Initialize FastMCP server
mcp = FastMCP("HappyFox")

# Configuration from Environment Variables
HAPPYFOX_DOMAIN = os.getenv("HAPPYFOX_DOMAIN") # e.g., "acme.happyfox.com"
API_KEY = os.getenv("HAPPYFOX_API_KEY")
AUTH_CODE = os.getenv("HAPPYFOX_AUTH_CODE")

BASE_URL = f"https://{HAPPYFOX_DOMAIN}/api/1.1/json"

def get_auth():
    """Returns the basic auth tuple used by HappyFox."""
    return (API_KEY, AUTH_CODE)

@mcp.tool()
def list_tickets(status: str = "_all", query: str = "", page: int = 1, size: int = 20) -> str:
    \"\"\"
    Fetch a list of tickets from HappyFox.
    - status: Use '_all', 'open', 'closed', etc.
    - query: Search string for the tickets.
    \"\"\"
    url = f"{BASE_URL}/tickets/"
    params = {
        "status": status,
        "q": query,
        "page": page,
        "size": size
    }
    
    response = requests.get(url, auth=get_auth(), params=params)
    if response.status_code == 200:
        tickets = response.json()
        return str(tickets)
    return f"Error fetching tickets: {response.status_code} - {response.text}"

@mcp.tool()
def get_ticket_details(ticket_id: int) -> str:
    \"\"\"Retrieve full details and history for a specific ticket ID.\"\"\"
    url = f"{BASE_URL}/tickets/{ticket_id}/"
    
    response = requests.get(url, auth=get_auth())
    if response.status_code == 200:
        return str(response.json())
    return f"Error fetching ticket {ticket_id}: {response.status_code}"

@mcp.tool()
def create_ticket(subject: str, message: str, contact_email: str) -> str:
    \"\"\"Create a new support ticket in HappyFox.\"\"\"
    url = f"{BASE_URL}/tickets/"
    payload = {
        "subject": subject,
        "message": message,
        "contact_email": contact_email
    }
    
    response = requests.post(url, auth=get_auth(), json=payload)
    if response.status_code in [200, 201]:
        return f"Ticket created successfully: {response.json()}"
    return f"Error creating ticket: {response.status_code} - {response.text}"

@mcp.tool()
def add_ticket_update(ticket_id: int, message: str, is_private: bool = False) -> str:
    \"\"\"
    Add a response or private note to an existing ticket.
    - is_private: If true, adds as a staff private note (ideal for drafting responses 
      for human confirmation before posting publicly); otherwise, a public update.
    \"\"\"
    endpoint = "staff_private_note" if is_private else "staff_update"
    url = f"{BASE_URL}/tickets/{ticket_id}/{endpoint}"
    
    payload = {"message": message}
    
    response = requests.post(url, auth=get_auth(), json=payload)
    if response.status_code in [200, 201]:
        return "Update added successfully."
    return f"Error updating ticket: {response.status_code} - {response.text}"

@mcp.tool()
def update_ticket(ticket_id: int, status_id: Optional[int] = None, priority_id: Optional[int] = None, category_id: Optional[int] = None) -> str:
    \"\"\"
    Update ticket attributes such as status (e.g., to close a ticket), priority, or category.
    - status_id: The ID of the new status. See list_statuses() for valid IDs.
    - priority_id: The ID of the new priority level.
    - category_id: The ID of the new category.
    \"\"\"
    url = f"{BASE_URL}/tickets/{ticket_id}"
    
    payload = {}
    if status_id is not None: payload["status"] = status_id
    if priority_id is not None: payload["priority"] = priority_id
    if category_id is not None: payload["category"] = category_id
    
    if not payload:
        return "No attributes provided for update."

    # HappyFox typically uses PUT or POST for updates depending on the specific field. 
    # Following standard REST practices for this API version's ticket modification.
    response = requests.put(url, auth=get_auth(), json=payload)
    if response.status_code in [200, 204]:
        return "Ticket attributes updated successfully."
    return f"Error updating ticket attributes: {response.status_code} - {response.text}"

@mcp.tool()
def list_statuses() -> str:
    \"\"\"Fetch all available ticket statuses to find IDs for 'Closed', 'Resolved', etc.\"\"\"
    url = f"{BASE_URL}/statuses/"
    response = requests.get(url, auth=get_auth())
    if response.status_code == 200:
        return str(response.json())
    return f"Error fetching statuses: {response.status_code} - {response.text}"

@mcp.tool()
def list_categories() -> str:
    \"\"\"Fetch all available ticket categories.\"\"\"
    url = f"{BASE_URL}/categories/"
    response = requests.get(url, auth=get_auth())
    if response.status_code == 200:
        return str(response.json())
    return f"Error fetching categories: {response.status_code} - {response.text}"

if __name__ == "__main__":
    mcp.run()

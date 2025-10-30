from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
import json
from datetime import datetime
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

app = FastAPI(title="Scheduler Bot API")

# File paths
CONTACTS_FILE = "contacts.json"
TRACKING_FILE = "email_tracking.json"

# Calendly link
CALENDLY_LINK = os.getenv("CALENDLY_LINK")


def load_json(filename):
    """Load JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


def save_json(filename, data):
    """Save data to JSON file"""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


def update_contact_status(contact_id, status):
    """Update contact status in contacts.json"""
    contacts = load_json(CONTACTS_FILE)
    for contact in contacts:
        if contact['id'] == contact_id:
            contact['status'] = status
            contact['updated_at'] = datetime.now().isoformat()
            break
    save_json(CONTACTS_FILE, contacts)


def track_response(contact_id, action):
    """Track email response in tracking file"""
    tracking = load_json(TRACKING_FILE)
    
    # Find the contact
    contacts = load_json(CONTACTS_FILE)
    contact = next((c for c in contacts if c['id'] == contact_id), None)
    
    if contact:
        tracking_entry = {
            "contact_id": contact_id,
            "contact_name": contact['name'],
            "contact_email": contact['email'],
            "action": action,
            "timestamp": datetime.now().isoformat()
        }
        tracking.append(tracking_entry)
        save_json(TRACKING_FILE, tracking)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Scheduler Bot API is running!",
        "endpoints": {
            "interested": "/interested/{contact_id}",
            "not_interested": "/not-interested/{contact_id}",
            "stats": "/stats"
        }
    }


@app.get("/interested/{contact_id}")
async def interested(contact_id: int):
    """Handle 'Interested' button click - redirect to Calendly"""
    
    # Update contact status
    update_contact_status(contact_id, "interested")
    
    # Track the response
    track_response(contact_id, "interested")
    
    # Redirect to Calendly
    return RedirectResponse(url=CALENDLY_LINK)


@app.get("/not-interested/{contact_id}")
async def not_interested(contact_id: int):
    """Handle 'Not Interested' button click"""
    
    # Update contact status
    update_contact_status(contact_id, "not_interested")
    
    # Track the response
    track_response(contact_id, "not_interested")
    
    # Return a thank you page
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Thank You</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .container {
                background: white;
                padding: 50px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                text-align: center;
                max-width: 500px;
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
            }
            p {
                color: #666;
                font-size: 16px;
                line-height: 1.6;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Thank You for Your Response</h1>
            <p>We appreciate you taking the time to respond.</p>
            <p>If you change your mind in the future, feel free to reach out to us anytime.</p>
            <p>Have a great day! 🙂</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/stats")
async def get_stats():
    """Get statistics about email campaigns"""
    contacts = load_json(CONTACTS_FILE)
    tracking = load_json(TRACKING_FILE)
    
    total_contacts = len(contacts)
    interested_count = len([c for c in contacts if c['status'] == 'interested'])
    not_interested_count = len([c for c in contacts if c['status'] == 'not_interested'])
    pending_count = len([c for c in contacts if c['status'] == 'pending'])
    
    return {
        "total_contacts": total_contacts,
        "interested": interested_count,
        "not_interested": not_interested_count,
        "pending": pending_count,
        "response_rate": f"{((interested_count + not_interested_count) / total_contacts * 100):.1f}%" if total_contacts > 0 else "0%",
        "recent_responses": tracking[-10:] if len(tracking) > 0 else []
    }


@app.get("/contacts")
async def get_contacts():
    """Get all contacts"""
    contacts = load_json(CONTACTS_FILE)
    return {"contacts": contacts, "total": len(contacts)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
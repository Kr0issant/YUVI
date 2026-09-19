# YUVI 🤖

**Utility & Ticket Management Discord Bot for Reinforce Club SST**

YUVI powers the Discord operations for Reinforce Club SST, featuring an asynchronous Firestore-backed **Support & Project Ticket System** designed to sync seamlessly with the Reinforce Web Dashboard.

---

## 🏗️ Architecture & Project Structure

```text
YUVI/
├── cogs/
│   ├── tickets.py            # Discord Cog for slash commands & real-time message sync
│   ├── auth.py               # (Future) Google account authentication & role linking
│   └── db.py                 # Quick DB utility commands
├── models/
│   ├── __init__.py
│   └── ticket.py             # Data classes, enums, & Firestore serialization models
├── utils/
│   ├── __init__.py
│   ├── firestore_client.py   # Shared Firestore client initializer
│   ├── ticket_manager.py     # Async CRUD operations for Firestore tickets
│   └── transcript_generator.py # Transcript generation (Text/Markdown)
├── views/
│   ├── __init__.py
│   ├── ticket_panel.py       # Persistent Category Dropdown Select Menu
│   ├── ticket_modals.py      # Category-tailored interactive modals & thread creation
│   └── ticket_controls.py   # In-thread controls (Claim, Add Member, Transcript, Close)
├── serviceAccountKey.json    # Firebase Admin credentials
├── yuvi_bot.py               # Main bot subclass and cog loader
├── main.py                   # Entry point
└── pyproject.toml            # Project dependencies
```

---

## 🎫 Ticket System Categories

| Category | Description | Modal Inputs |
|---|---|---|
| **🚀 SPG Registration / Modification** | Student Project Groups (Product, Kaggle, Research) | Project Name & Track, Team Leader & Members, Estimated Duration, Goals & Summary |
| **⚡ Resource Request** | Cloud/GPU compute, API credits, hardware, mentorship | Project Name, Resources Needed, Progress Proof Links, Justification |
| **💬 Support & Inquiries** | General questions about events, workshops, tracks | Subject, Detailed Question |
| **💡 Idea Jar & Suggestions** | Proposing projects for community or club suggestions | Idea Title, Target Track, Concept & Learning Objectives |
| **🛡️ Report Issue / Misconduct** | Confidential reports for rule violations | Incident Summary, Confidential Details |
| **📦 General / Misc** | Any other inquiries | Subject, Details |

---

## ⚡ Real-Time Firestore Synchronization

- **Collection:** `tickets/{ticket_id}` (Auto-generated Firestore Document ID)
- **Subcollection:** `tickets/{ticket_id}/messages/{message_id}`
- Every message and attachment sent inside a ticket thread on Discord is asynchronously written to Firestore with:
  - `sender_id`, `sender_name`, `sender_role` (`admin`, `lead`, `user`)
  - `source`: `"discord"`
  - `content`: message body
  - `attachments`: list of uploaded file/image URLs
  - `timestamp`: server timestamp
- The **Reinforce Web Dashboard** can read and write to this same structure to enable two-way communication between the website and Discord.

---

## 🛠️ Slash Commands

### Deployment
- `/setup-tickets [channel]` *(Admin only)*: Deploys the interactive ticket panel with the category dropdown.

### Ticket Thread Controls
- `/ticket close [reason]`: Closes the ticket, archives the thread, and uploads the transcript.
- `/ticket claim`: Claims the ticket for the interacting admin/lead.
- `/ticket add <member>`: Adds a collaborator or team member to the private ticket thread.
- `/ticket remove <member>`: Removes a user from the ticket thread.
- `/ticket transcript`: Exports and downloads the complete chat transcript.
- `/ticket info`: Displays Firestore database metadata for the active ticket.
- `/ticket list [status] [category]` *(Admin only)*: Lists active tickets stored in Firestore.

---

## 🚀 Setup & Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Configure environment variables in `.env`:
   - `DISCORD_TOKEN`: Your Discord Bot Token
   - `GUILD_ID`: Your Discord Server Guild ID
   - `TICKETS_CHANNEL_ID`: Channel ID where ticket private threads are created
   - `ADMIN_ROLE_ID` / `SUPPORT_ROLE_ID`: Role IDs for admins and track leads
   - `TRANSCRIPTS_CHANNEL_ID`: (Optional) Channel ID to log closed ticket transcripts
   - `GOOGLE_APPLICATION_CREDENTIALS`: Path to Firebase `serviceAccountKey.json`

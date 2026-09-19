import io
from datetime import datetime
from typing import List, Optional
from models.ticket import Ticket, TicketMessage

class TranscriptGenerator:
    @staticmethod
    def generate_text_transcript(ticket: Ticket, messages: List[TicketMessage]) -> io.BytesIO:
        """Generates a clean text/markdown transcript file."""
        lines = []
        lines.append("=" * 70)
        lines.append(f"REINFORCE CLUB - TICKET TRANSCRIPT")
        lines.append(f"Ticket ID:   {ticket.id}")
        lines.append(f"Category:    {ticket.category.label if hasattr(ticket.category, 'label') else ticket.category}")
        lines.append(f"Subject:     {ticket.title}")
        lines.append(f"Status:      {ticket.status.label if hasattr(ticket.status, 'label') else ticket.status}")
        if ticket.created_by:
            lines.append(f"Created By:  {ticket.created_by.username} ({ticket.created_by.discord_id})")
        if ticket.assigned_to:
            lines.append(f"Assigned To: {ticket.assigned_to.username} ({ticket.assigned_to.discord_id})")
        if ticket.closed_by:
            lines.append(f"Closed By:   {ticket.closed_by.username} ({ticket.closed_by.discord_id})")
        if ticket.close_reason:
            lines.append(f"Close Reason: {ticket.close_reason}")
        lines.append("=" * 70)
        lines.append("")
        
        if ticket.fields:
            lines.append("--- Initial Submission Fields ---")
            for k, v in ticket.fields.items():
                lines.append(f"{k.capitalize()}: {v}")
            lines.append("-" * 35)
            lines.append("")

        lines.append("--- Conversation History ---")
        if not messages:
            lines.append("[No messages recorded]")
        else:
            for msg in messages:
                ts_str = ""
                if msg.timestamp:
                    if isinstance(msg.timestamp, datetime):
                        ts_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
                    else:
                        ts_str = str(msg.timestamp)
                
                header = f"[{ts_str}] [{msg.source.upper()}] {msg.sender_name} ({msg.sender_role})"
                lines.append(header)
                if msg.content:
                    for c_line in msg.content.splitlines():
                        lines.append(f"  {c_line}")
                if msg.attachments:
                    for att in msg.attachments:
                        lines.append(f"  [Attachment: {att}]")
                lines.append("")

        lines.append("=" * 70)
        lines.append("End of transcript.")
        
        content = "\n".join(lines)
        buffer = io.BytesIO(content.encode("utf-8"))
        buffer.seek(0)
        return buffer

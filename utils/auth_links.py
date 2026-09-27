"""One-time proof that the link recipient controls a Discord account."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from urllib.parse import urlencode, urlsplit, urlunsplit
from fastapi import HTTPException


def issue_link(db, discord_id, frontend_url, now=None):
    now = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.collection('discord_link_tokens').document(sha256(token.encode()).hexdigest()).create({
        'discord_id': str(discord_id),
        'issued_at': now,
        'expires_at': now + timedelta(minutes=10),
        'consumed_by': None,
    })
    url = urlsplit(frontend_url)
    return urlunsplit((url.scheme, url.netloc, url.path, '', urlencode({'link_token': token})))


def require_verified_link(db, discord_id, email):
    email = email.lower().strip()
    discord_id = str(discord_id).strip()
    query = db.collection('users').where('discord_id', '==', discord_id).where('email', '==', email).limit(1)
    docs = list(query.stream())
    if not docs and discord_id.isdigit():
        query_int = db.collection('users').where('discord_id', '==', int(discord_id)).where('email', '==', email).limit(1)
        docs = list(query_int.stream())
    if not docs:
        query_email = db.collection('users').where('email', '==', email).limit(1)
        docs_email = list(query_email.stream())
        if docs_email:
            rec = docs_email[0].to_dict() or {}
            if str(rec.get('discord_id') or '').strip() == discord_id and rec.get('discord_link_version') == 1:
                return
        raise HTTPException(403, 'A verified Discord link is required.')
    record = docs[0].to_dict() or {}
    if record.get('discord_link_version') != 1:
        raise HTTPException(403, 'A verified Discord link is required.')

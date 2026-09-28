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
    """Accept only the canonical UID profile linked to this Discord account."""
    if not verified_uid_for_discord(db, discord_id, email):
        raise HTTPException(403, 'A verified Discord link is required.')


def verified_uid_for_discord(db, discord_id, email=None):
    """Resolve a proven Discord link to its canonical Firebase UID.

    Older email/Discord lookup documents can remain in the shared collection;
    they are never proof of ownership or a ticket creator identity.
    """
    discord_id = str(discord_id).strip()
    if not discord_id.isdigit():
        return None
    expected_email = str(email).lower().strip() if email else None
    matches = {}
    for stored_id in (discord_id, int(discord_id)):
        query = db.collection('users').where('discord_id', '==', stored_id)
        for doc in query.stream():
            record = doc.to_dict() or {}
            if record.get('id') != doc.id or record.get('discord_link_version') != 1:
                continue
            if record.get('firebase_uid') not in (None, doc.id):
                continue
            record_email = str(record.get('email') or '').lower().strip()
            if not record_email:
                continue
            if str(record.get('discord_id') or '').strip() == discord_id:
                matches[doc.id] = record_email
    if len(matches) != 1:
        return None
    uid, actual_email = next(iter(matches.items()))
    return uid if not expected_email or actual_email == expected_email else None

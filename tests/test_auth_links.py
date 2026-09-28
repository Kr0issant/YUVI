import asyncio
import unittest
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit, parse_qs
from unittest.mock import MagicMock
from utils.auth_links import issue_link, require_verified_link, verified_uid_for_discord
from utils.user_manager import UserManager
from fastapi import HTTPException


class UsersQuery:
    def __init__(self, records, filters=()):
        self.records = records
        self.filters = filters

    def where(self, field, _operator, value):
        return UsersQuery(self.records, (*self.filters, (field, value)))

    def stream(self):
        for key, data in self.records.items():
            if all(data.get(field) == value for field, value in self.filters):
                yield self.document(key).get()

    def document(self, key):
        records = self.records

        class UserRef:
            def get(self):
                data = records.get(key)
                return type('UserDoc', (), {
                    'id': key,
                    'exists': data is not None,
                    'to_dict': lambda _self: data,
                })()

        return UserRef()


class UsersDB:
    def __init__(self, records):
        self.records = records

    def collection(self, name):
        assert name == 'users'
        return UsersQuery(self.records)


class AuthLinkTests(unittest.TestCase):
    def test_private_token_is_hashed_short_lived_and_only_in_fragment(self):
        db = MagicMock()
        now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        url = issue_link(db, '123456789012345678', 'https://club.example/auth', now)
        parsed = urlsplit(url)
        token = parse_qs(parsed.fragment)['link_token'][0]
        self.assertEqual(parsed.query, '')
        self.assertGreaterEqual(len(token), 43)
        db.collection.assert_called_once_with('discord_link_tokens')
        db.collection.return_value.document.assert_called_once_with(sha256(token.encode()).hexdigest())
        data = db.collection.return_value.document.return_value.create.call_args.args[0]
        self.assertEqual(data['discord_id'], '123456789012345678')
        self.assertEqual((data['expires_at'] - now).total_seconds(), 600)
        self.assertNotIn(token, repr(data))
    def test_webhook_rejects_unproven_link(self):
        db = UsersDB({'uid-1': {'id': 'uid-1', 'email': 'member@sst.scaler.com', 'discord_id': '123'}})
        with self.assertRaises(HTTPException): require_verified_link(db, '123', 'member@sst.scaler.com')

    def test_alias_alone_cannot_prove_a_link(self):
        alias = {'email': 'member@sst.scaler.com', 'discord_id': '123', 'discord_link_version': 1, 'firebase_uid': 'uid-1'}
        db = UsersDB({'123': alias, 'member@sst.scaler.com': alias})
        with self.assertRaises(HTTPException): require_verified_link(db, '123', 'member@sst.scaler.com')

    def test_canonical_link_resolves_uid_even_with_stale_aliases(self):
        email = 'member@sst.scaler.com'
        db = UsersDB({
            '123': {'email': email, 'discord_id': '123', 'discord_link_version': 1, 'firebase_uid': 'other'},
            'uid-1': {'id': 'uid-1', 'email': email, 'discord_id': '123', 'discord_link_version': 1},
        })
        require_verified_link(db, '123', email)
        self.assertEqual(verified_uid_for_discord(db, '123'), 'uid-1')
        with self.assertRaises(HTTPException): require_verified_link(db, '123', 'different@sst.scaler.com')

    def test_duplicate_canonical_links_are_not_assigned_to_either_user(self):
        db = UsersDB({
            'uid-1': {'id': 'uid-1', 'email': 'one@sst.scaler.com', 'discord_id': '123', 'discord_link_version': 1},
            'uid-2': {'id': 'uid-2', 'email': 'two@sst.scaler.com', 'discord_id': '123', 'discord_link_version': 1},
        })
        self.assertIsNone(verified_uid_for_discord(db, '123'))

    def test_member_lookup_ignores_old_aliases(self):
        email = 'member@sst.scaler.com'
        db = UsersDB({
            '123': {'email': email, 'discord_id': '123', 'discord_link_version': 1, 'firebase_uid': 'stale'},
            email: {'email': email, 'discord_id': '123', 'discord_link_version': 1, 'firebase_uid': 'stale'},
            'uid-1': {'id': 'uid-1', 'email': email, 'discord_id': '123', 'discord_link_version': 1},
        })
        with unittest.mock.patch.object(UserManager, '_get_db', return_value=db):
            self.assertEqual(asyncio.run(UserManager.get_user('123'))['doc_id'], 'uid-1')
            self.assertEqual(asyncio.run(UserManager.get_user_by_email(email))['doc_id'], 'uid-1')

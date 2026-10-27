import os
import asyncio
import unittest
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import server
from models.idea import Idea
from models.ticket import Ticket, TicketMessage, TicketUser, TicketStatus
from utils.idea_manager import IdeaManager
from utils.ticket_manager import TicketManager
from utils.user_manager import UserManager
from views.ticket_controls import TicketControlView
from views.ticket_panel import TicketCategorySelect
from views.ticket_modals import create_ticket_thread_and_doc
from cogs.tickets import TicketsCog


class FakeIdeaDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class FakeIdeaQuery:
    def __init__(self, docs, predicate=lambda _data: True, limit=None):
        self.docs = docs
        self.predicate = predicate
        self.limit_count = limit

    def where(self, field, _operator, value):
        return FakeIdeaQuery(
            self.docs,
            lambda data: self.predicate(data) and data.get(field) == value,
            self.limit_count,
        )

    def limit(self, count):
        return FakeIdeaQuery(self.docs, self.predicate, count)

    def stream(self):
        matches = [doc for doc in self.docs if self.predicate(doc.to_dict())]
        return matches[: self.limit_count]


class FakeIdeaDB:
    def __init__(self, docs):
        self.query = FakeIdeaQuery(docs)

    def collection(self, _name):
        return self.query


class FakeMessageCollection:
    def __init__(self):
        self.requested_id = None
        self.saved = None
        self.direction = None

    def document(self, doc_id=None):
        self.requested_id = doc_id
        collection = self

        class Ref:
            id = doc_id or "auto-id"

            def get(self):
                return SimpleNamespace(exists=collection.saved is not None)

            def set(self, data):
                collection.saved = data

        return Ref()

    def order_by(self, _field, direction=None):
        self.direction = direction
        return self

    def limit(self, _count):
        return self

    def stream(self):
        return [
            FakeIdeaDoc("new", {"sender_uid": "u", "timestamp": 2}),
            FakeIdeaDoc("old", {"sender_uid": "u", "timestamp": 1}),
        ]


class FakeTicketRef:
    def __init__(self):
        self.messages = FakeMessageCollection()

    def collection(self, _name):
        return self.messages

    def update(self, _updates):
        pass


class FakeTicketDB:
    def __init__(self):
        self.ticket = FakeTicketRef()

    def collection(self, _name):
        db = self

        class Tickets:
            def document(self, _ticket_id):
                return db.ticket

        return Tickets()


class FakeThread:
    def __init__(self):
        self.id = 333
        self.add_user = AsyncMock()
        self.send = AsyncMock(return_value=SimpleNamespace(id=444))


class FakeChannel:
    def __init__(self):
        self.id = 222
        self.thread = FakeThread()
        self.threads = []
        self.create_thread = AsyncMock(return_value=self.thread)


class FakeGuild:
    def __init__(self):
        self.id = 111
        self.channel = FakeChannel()
        self.member = SimpleNamespace(id=555, mention="<@555>")
        self.roles = []
        self.icon = None

    def get_channel(self, channel_id):
        return self.channel if channel_id == self.channel.id else None

    def get_member(self, member_id):
        return self.member if member_id == self.member.id else None


class FakeBot:
    def __init__(self, guild):
        self.guild = guild
        self.guilds = [guild]
        self.relay_thread = guild.channel.thread

    def is_ready(self):
        return True

    def get_guild(self, guild_id):
        return self.guild if guild_id == self.guild.id else None

    def get_channel(self, channel_id):
        return self.relay_thread if channel_id == self.relay_thread.id else None


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.guild = FakeGuild()
        self.bot = FakeBot(self.guild)
        self.client = TestClient(server.app)
        self.env = patch.dict(
            os.environ,
            {
                "BOT_INTERNAL_SECRET": "bridge-secret",
                "GUILD_ID": "111",
                "TICKETS_CHANNEL_ID": "222",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_bridge_routes_require_secret(self):
        create_payload = {
            "ticket_id": "tkt-1", "category": "support", "title": "Help", "creator_uid": "uid-1"
        }
        relay_payload = {
            "ticket_id": "tkt-1", "thread_id": "333", "sender_uid": "uid-1", "content": "Hello"
        }
        for path in ("/tickets/create-thread", "/internal/tickets/create-thread", "/internal/tickets/thread-create"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json=create_payload).status_code, 401)
        for path in ("/tickets/relay-message", "/internal/tickets/relay-message", "/internal/tickets/message-out"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json=relay_payload).status_code, 401)

    def test_create_thread_adds_member_and_persists_metadata(self):
        with (
            patch.object(server, "bot", self.bot),
            patch.object(server, "user_discord_id", AsyncMock(return_value="555")),
            patch.object(
                server.TicketManager,
                "reserve_thread_creation",
                AsyncMock(return_value={"status": "reserved"}),
            ),
            patch.object(server.TicketManager, "update_ticket", AsyncMock()) as update,
        ):
            response = self.client.post(
                "/tickets/create-thread",
                headers={"X-Internal-Secret": "bridge-secret"},
                json={
                    "ticket_id": "tkt-1",
                    "category": "support",
                    "title": "Help",
                    "creator_uid": "uid-1",
                    "fields": {"topic": "Auth"},
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["discord_meta"]["thread_id"], "333")
        self.guild.channel.thread.add_user.assert_awaited_once_with(self.guild.member)
        self.assertEqual(update.await_count, 2)

    def test_create_thread_retry_returns_existing_metadata(self):
        with patch.object(
            server.TicketManager,
            "reserve_thread_creation",
            AsyncMock(
                return_value={
                    "status": "existing",
                    "discord_meta": {
                        "guild_id": "111",
                        "channel_id": "222",
                        "thread_id": "333",
                    },
                }
            ),
        ):
            response = self.client.post(
                "/tickets/create-thread",
                headers={"X-Internal-Secret": "bridge-secret"},
                json={
                    "ticket_id": "tkt-1",
                    "category": "support",
                    "title": "Help",
                    "creator_uid": "uid-1",
                },
            )
        self.assertTrue(response.json()["existing"])

    def test_incomplete_thread_setup_is_resumed(self):
        with (
            patch.object(server, "bot", self.bot),
            patch.object(server, "user_discord_id", AsyncMock(return_value="555")),
            patch.object(
                server.TicketManager,
                "reserve_thread_creation",
                AsyncMock(
                    return_value={
                        "status": "resume",
                        "discord_meta": {
                            "guild_id": "111",
                            "channel_id": "222",
                            "thread_id": "333",
                        },
                    }
                ),
            ),
            patch.object(server.TicketManager, "update_ticket", AsyncMock()) as update,
        ):
            response = self.client.post(
                "/tickets/create-thread",
                headers={"X-Internal-Secret": "bridge-secret"},
                json={
                    "ticket_id": "tkt-1",
                    "category": "support",
                    "title": "Help",
                    "creator_uid": "uid-1",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.guild.channel.create_thread.assert_not_awaited()
        self.guild.channel.thread.add_user.assert_awaited_once()
        self.assertEqual(update.await_count, 2)

    def test_failed_thread_setup_releases_reservation(self):
        with (
            patch.object(server.TicketManager, "reserve_thread_creation", AsyncMock(return_value={"status": "reserved"})),
            patch.object(server.TicketManager, "release_thread_creation", AsyncMock()) as release,
            patch.object(server, "ready_guild", AsyncMock(side_effect=server.HTTPException(status_code=503, detail="offline"))),
        ):
            response = self.client.post(
                "/tickets/create-thread",
                headers={"X-Internal-Secret": "bridge-secret"},
                json={"ticket_id": "tkt-1", "category": "support", "title": "Help", "creator_uid": "uid-1"},
            )
        self.assertEqual(response.status_code, 503)
        release.assert_awaited_once_with("tkt-1")

    def test_relay_validates_link_and_sends_message(self):
        ticket = SimpleNamespace(thread_id="333", discord_meta=None)
        with (
            patch.object(server, "bot", self.bot),
            patch.object(
                server.TicketManager, "get_ticket", AsyncMock(return_value=ticket)
            ),
        ):
            response = self.client.post(
                "/tickets/relay-message",
                headers={"X-Internal-Secret": "bridge-secret"},
                json={
                    "ticket_id": "tkt-1",
                    "thread_id": "333",
                    "sender_uid": "uid-1",
                    "content": "Hello",
                    "attachments": ["https://example.test/file"],
                },
            )
        self.assertEqual(response.status_code, 200)
        sent = self.guild.channel.thread.send.await_args.args[0]
        self.assertIn("Hello", sent)
        self.assertIn("https://example.test/file", sent)

    def test_thread_creator_must_have_this_uid_verified(self):
        discord_id = "555"
        email = "member@sst.scaler.com"
        records = {
            "uid-1": {"id": "uid-1", "email": email, "discord_id": "other", "discord_link_version": 1},
            discord_id: {"email": email, "discord_id": discord_id, "discord_link_version": 1, "firebase_uid": "uid-2"},
            email: {"email": email, "discord_id": discord_id, "discord_link_version": 1, "firebase_uid": "uid-2"},
        }
        db = MagicMock()
        def document(key):
            data = records.get(key)
            return SimpleNamespace(get=lambda: SimpleNamespace(exists=data is not None, to_dict=lambda: data))
        db.collection.return_value.document.side_effect = document
        db.collection.return_value.where.side_effect = lambda field, _op, value: FakeIdeaQuery(
            [FakeIdeaDoc(key, data) for key, data in records.items()]
        ).where(field, "==", value)
        with patch.object(server, "get_firestore_client", return_value=db):
            with self.assertRaises(server.HTTPException) as error:
                asyncio.run(server.user_discord_id("uid-1"))
            self.assertEqual(error.exception.status_code, 409)
            records["uid-1"]["discord_id"] = discord_id
            self.assertEqual(asyncio.run(server.user_discord_id("uid-1")), discord_id)


class IdeaContractTests(unittest.TestCase):
    def test_idea_dual_writes_dashboard_contract(self):
        idea = Idea(
            title="Idea",
            description="Description",
            track="other",
            rough_roadmap=["Step one"],
            is_approved=True,
            created_by_uid="uid-1",
            created_by=TicketUser(discord_id="555", username="Member"),
        )
        data = idea.to_dict()
        self.assertTrue(data["is_verified"])
        self.assertEqual(data["rough_roadmap"], ["Step one"])
        self.assertEqual(data["created_by_uid"], "uid-1")

    def test_idea_reads_dashboard_contract(self):
        idea = Idea.from_dict(
            "idea-1",
            {
                "title": "Idea",
                "description": "Description",
                "track": "misc",
                "rough_roadmap": ["Step one"],
                "is_verified": True,
                "created_by_uid": "uid-1",
            },
        )
        self.assertTrue(idea.is_approved)
        self.assertEqual(idea.roadmap, ["Step one"])
        self.assertEqual(idea.track, "misc")

    def test_idea_normalizes_optional_dashboard_display_fields(self):
        idea = Idea.from_dict(
            "idea-1", {"title": "Idea", "track": None, "difficulty": None}
        )
        self.assertEqual(idea.track, "misc")
        self.assertEqual(idea.difficulty, "intermediate")

    def test_manager_unions_canonical_and_legacy_approval_fields(self):
        db = FakeIdeaDB(
            [
                FakeIdeaDoc(
                    "canonical", {"title": "A", "track": "misc", "is_verified": True}
                ),
                FakeIdeaDoc(
                    "legacy", {"title": "B", "track": "other", "is_approved": True}
                ),
            ]
        )
        with patch.object(IdeaManager, "_get_db", return_value=db):
            ideas = asyncio.run(IdeaManager.list_ideas(track="other"))
        self.assertEqual({idea.id for idea in ideas}, {"canonical", "legacy"})

    def test_discord_idea_uses_member_uid_without_member_create_endpoint(self):
        db = MagicMock()
        db.collection.return_value.document.return_value.id = "idea-1"
        idea = Idea(title="Idea", created_by=TicketUser(discord_id="555", username="Member"))
        with (
            patch.object(IdeaManager, "_get_db", return_value=db),
            patch("utils.idea_manager._user_uid", return_value="uid-1"),
            patch("utils.idea_manager.APIClient.post", AsyncMock()) as member_post,
        ):
            idea_id = asyncio.run(IdeaManager.create_idea(idea))
        self.assertEqual(idea_id, "idea-1")
        self.assertEqual(db.collection.return_value.document.return_value.set.call_args.args[0]["created_by_uid"], "uid-1")
        member_post.assert_not_awaited()

    def test_discord_approval_uses_admin_uid_without_member_approve_endpoint(self):
        db = MagicMock()
        idea_ref = db.collection.return_value.document.return_value
        idea_ref.get.return_value.exists = True
        admin = TicketUser(discord_id="777", username="Admin")
        with (
            patch.object(IdeaManager, "_get_db", return_value=db),
            patch("utils.idea_manager._user_uid", return_value="admin-uid"),
            patch("utils.idea_manager.APIClient.post", AsyncMock()) as member_post,
        ):
            approved = asyncio.run(IdeaManager.approve_idea("idea-1", admin))
        self.assertTrue(approved)
        self.assertEqual(idea_ref.update.call_args.args[0]["approved_by_uid"], "admin-uid")
        member_post.assert_not_awaited()


class TicketContractTests(unittest.TestCase):
    def test_existing_legacy_thread_is_not_created_again(self):
        db = MagicMock()
        ticket_ref = db.collection.return_value.document.return_value
        ticket_ref.get.return_value = SimpleNamespace(
            exists=True,
            to_dict=lambda: {
                "discord_meta": {"guild_id": "111", "channel_id": "222", "thread_id": "333"}
            },
        )
        with (
            patch.object(TicketManager, "_get_db", return_value=db),
            patch("utils.ticket_manager.firestore.transactional", side_effect=lambda fn: fn),
        ):
            result = asyncio.run(TicketManager.reserve_thread_creation("ticket-1"))
        self.assertEqual(result["status"], "existing")
        db.transaction.return_value.update.assert_not_called()

    def test_dashboard_identity_fields_are_read(self):
        ticket = Ticket.from_dict(
            "ticket-1", {"created_by_uid": "uid-1", "category": "feedback"}
        )
        message = TicketMessage.from_dict(
            "message-1", {"sender_uid": "uid-2", "content": "Hello"}
        )
        self.assertEqual(ticket.created_by_uid, "uid-1")
        self.assertEqual(ticket.category.value, "feedback")
        self.assertEqual(message.sender_id, "uid-2")

    def test_discord_messages_are_idempotent_and_latest_window_is_chronological(self):
        db = FakeTicketDB()
        message = TicketMessage(
            sender_id="discord-user",
            sender_name="Member",
            content="Hello",
            discord_message_id="987654321",
        )
        with (
            patch.object(TicketManager, "_get_db", return_value=db),
            patch("utils.ticket_manager.APIClient.post", AsyncMock(return_value=None)),
        ):
            message_id = asyncio.run(
                TicketManager.add_ticket_message("ticket-1", message)
            )
            original = dict(db.ticket.messages.saved)
            message.content = "Changed replay"
            asyncio.run(TicketManager.add_ticket_message("ticket-1", message))
            messages = asyncio.run(TicketManager.get_ticket_messages("ticket-1"))
        expected_id = f"msg_discord_{sha256(b'987654321').hexdigest()[:24]}"
        self.assertEqual(message_id, expected_id)
        self.assertEqual(db.ticket.messages.requested_id, expected_id)
        self.assertEqual(db.ticket.messages.saved, original)
        self.assertEqual([item.id for item in messages], ["old", "new"])

    def test_bot_sync_response_does_not_write_a_duplicate_message(self):
        message = TicketMessage(sender_id="discord-user", sender_name="Member", content="Hello", discord_message_id="987654321")
        with (
            patch("utils.ticket_manager.APIClient.post", AsyncMock(return_value={"success": True, "message_id": "msg_discord_existing"})),
            patch.object(TicketManager, "_get_db", side_effect=AssertionError("fallback must not write")),
        ):
            message_id = asyncio.run(TicketManager.add_ticket_message("ticket-1", message))
        self.assertEqual(message_id, "msg_discord_existing")

    def test_discord_ticket_stores_verified_creator_without_reentering_member_api(self):
        db = MagicMock()
        db.collection.return_value.document.return_value.id = "ticket-1"
        ticket = Ticket(created_by=TicketUser(discord_id="555", username="Member"))
        with (
            patch("utils.ticket_manager.APIClient.post", AsyncMock()) as member_post,
            patch("utils.ticket_manager.verified_uid_for_discord", return_value="uid-1"),
            patch.object(TicketManager, "_get_db", return_value=db),
        ):
            ticket_id = asyncio.run(TicketManager.create_ticket(ticket))
        self.assertEqual(ticket_id, "ticket-1")
        self.assertEqual(db.collection.return_value.document.return_value.set.call_args.args[0]["created_by_uid"], "uid-1")
        member_post.assert_not_awaited()

    def test_discord_ticket_stores_verified_member_full_name(self):
        db = MagicMock()
        db.collection.return_value.document.return_value.id = "ticket-1"
        u_doc = MagicMock()
        u_doc.exists = True
        u_doc.to_dict.return_value = {"full_name": "Verified Jane", "email": "jane@sst.scaler.com"}

        def doc_side_effect(doc_id=None):
            mock_doc = MagicMock()
            if doc_id == "uid-1":
                mock_doc.get.return_value = u_doc
            else:
                mock_doc.id = "ticket-1"
            return mock_doc

        db.collection.return_value.document.side_effect = doc_side_effect
        ticket = Ticket(created_by=TicketUser(discord_id="555", username="Member"))
        with (
            patch("utils.ticket_manager.APIClient.post", AsyncMock()) as member_post,
            patch("utils.ticket_manager.verified_uid_for_discord", return_value="uid-1"),
            patch.object(TicketManager, "_get_db", return_value=db),
        ):
            ticket_id = asyncio.run(TicketManager.create_ticket(ticket))
        self.assertEqual(ticket_id, "ticket-1")
        self.assertEqual(ticket.created_by_name, "Verified Jane")
        self.assertEqual(ticket.created_by_email, "jane@sst.scaler.com")
        member_post.assert_not_awaited()

    def test_discord_claim_and_close_use_member_uids_without_member_close_endpoint(self):
        db = MagicMock()
        ticket_ref = db.collection.return_value.document.return_value
        member = TicketUser(discord_id="555", username="Member")
        with (
            patch.object(TicketManager, "_get_db", return_value=db),
            patch("utils.ticket_manager.verified_uid_for_discord", return_value="uid-1"),
            patch("utils.ticket_manager.APIClient.post", AsyncMock()) as member_post,
        ):
            self.assertTrue(asyncio.run(TicketManager.claim_ticket("ticket-1", member)))
            self.assertEqual(ticket_ref.update.call_args.args[0]["assigned_to_uid"], "uid-1")
            self.assertTrue(asyncio.run(TicketManager.close_ticket("ticket-1", member, "Done")))
            self.assertEqual(ticket_ref.update.call_args.args[0]["closed_by_uid"], "uid-1")
        member_post.assert_not_awaited()

    def test_ticket_control_claim_button_adds_admin_to_thread(self):
        import discord
        view = TicketControlView()
        interaction = MagicMock(spec=discord.Interaction)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 123456
        thread.add_user = AsyncMock()
        interaction.channel = thread
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 999
        interaction.user.name = "AdminUser"
        interaction.user.display_avatar = None
        interaction.user.mention = "<@999>"
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        ticket = Ticket(id="ticket-1", status=TicketStatus.OPEN, thread_id="123456")

        with (
            patch.object(TicketManager, "get_ticket_by_thread_id", AsyncMock(return_value=ticket)),
            patch.object(TicketManager, "claim_ticket", AsyncMock(return_value=True)),
        ):
            asyncio.run(view.claim_button.callback(interaction))

        thread.add_user.assert_awaited_once_with(interaction.user)
        interaction.response.send_message.assert_awaited_once()

    def test_slash_ticket_claim_adds_admin_to_thread(self):
        import discord
        cog = TicketsCog(MagicMock())
        interaction = MagicMock(spec=discord.Interaction)
        thread = MagicMock(spec=discord.Thread)
        thread.id = 123456
        thread.add_user = AsyncMock()
        interaction.channel = thread
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 999
        interaction.user.name = "AdminUser"
        interaction.user.display_avatar = None
        interaction.user.mention = "<@999>"
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        ticket = Ticket(id="ticket-1", status=TicketStatus.OPEN, thread_id="123456")

        with (
            patch.object(TicketManager, "get_ticket_by_thread_id", AsyncMock(return_value=ticket)),
            patch.object(TicketManager, "claim_ticket", AsyncMock(return_value=True)),
        ):
            asyncio.run(cog.ticket_claim.callback(cog, interaction))

        thread.add_user.assert_awaited_once_with(interaction.user)
        interaction.response.send_message.assert_awaited_once()

    def test_user_manager_is_user_verified_by_role(self):
        import discord
        user = MagicMock(spec=discord.Member)
        verified_role = MagicMock()
        verified_role.name = "Verified Member"
        verified_role.id = 111111
        user.roles = [verified_role]
        user.guild_permissions.administrator = False

        self.assertTrue(asyncio.run(UserManager.is_user_verified(user)))

    def test_user_manager_is_user_verified_by_db(self):
        import discord
        user = MagicMock(spec=discord.Member)
        user.id = 12345
        user.roles = []
        user.guild_permissions.administrator = False

        db = MagicMock()
        with (
            patch.object(UserManager, "_get_db", return_value=db),
            patch("utils.user_manager.verified_uid_for_discord", return_value="uid-12345"),
        ):
            self.assertTrue(asyncio.run(UserManager.is_user_verified(user)))

    def test_user_manager_unverified_returns_false(self):
        import discord
        user = MagicMock(spec=discord.Member)
        user.id = 99999
        user.roles = []
        user.guild_permissions.administrator = False

        db = MagicMock()
        with (
            patch.object(UserManager, "_get_db", return_value=db),
            patch("utils.user_manager.verified_uid_for_discord", return_value=None),
        ):
            self.assertFalse(asyncio.run(UserManager.is_user_verified(user)))

    def test_ticket_category_select_blocks_unverified_user(self):
        import discord
        select = TicketCategorySelect()
        select._values = ["spg_registration"]
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 99999
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.send_modal = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()

        with patch.object(UserManager, "is_user_verified", AsyncMock(return_value=False)):
            asyncio.run(select.callback(interaction))

        interaction.response.send_message.assert_awaited_once()
        self.assertIn("Verification Required", interaction.response.send_message.call_args.args[0])
        interaction.response.send_modal.assert_not_awaited()

    def test_create_ticket_thread_and_doc_blocks_unverified_user(self):
        import discord
        from models.ticket import TicketCategory
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 99999
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch.object(UserManager, "is_user_verified", AsyncMock(return_value=False)):
            asyncio.run(create_ticket_thread_and_doc(
                interaction=interaction,
                category=TicketCategory.SUPPORT,
                title="Help needed",
                description="Need help",
                fields={}
            ))

        interaction.followup.send.assert_awaited_once()
        self.assertIn("Verification Required", interaction.followup.send.call_args.args[0])
        interaction.guild.get_channel.assert_not_called()


if __name__ == "__main__":
    unittest.main()

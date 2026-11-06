import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from datetime import datetime, timezone
import discord

from cogs.tickets import TicketsCog
from views.ticket_controls import CloseReasonModal
from models.ticket import Ticket, TicketCategory, TicketStatus, TicketUser


class FakeTicketThread(AsyncMock):
    def __init__(self, thread_id=987654321):
        super().__init__(spec=discord.Thread)
        self.id = thread_id
        self.name = "test-ticket-thread"
        self.send = AsyncMock()
        self.edit = AsyncMock()


class TicketLifecycleTestSuite(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.add_view = MagicMock()
        self.cog = TicketsCog(self.bot)

    def _create_mock_ticket(self, ticket_id="ticket-101", status=TicketStatus.OPEN):
        return Ticket(
            id=ticket_id,
            category=TicketCategory.SUPPORT,
            title="Help with environment setup",
            description="Details",
            status=status,
            created_by=TicketUser(discord_id="12345", username="Alice"),
        )

    @patch("cogs.tickets.TicketPanelView")
    async def test_setup_tickets_deploys_official_panel(self, mock_panel_view):
        interaction = AsyncMock()
        target_channel = AsyncMock(spec=discord.TextChannel)
        target_channel.send = AsyncMock()
        target_channel.mention = "#tickets"

        await self.cog.setup_tickets.callback(self.cog, interaction, channel=target_channel)

        target_channel.send.assert_called_once()
        sent_embed = target_channel.send.call_args[1]["embed"]
        self.assertIn("Reinforce Club Support & Ticket System", sent_embed.title)
        self.assertIn("SPG Registration", sent_embed.description)
        interaction.response.send_message.assert_called_once()

    @patch("cogs.tickets.TicketManager.get_ticket_by_thread_id", new_callable=AsyncMock)
    @patch("cogs.tickets.TicketManager.close_ticket", new_callable=AsyncMock)
    @patch("cogs.tickets.TicketManager.get_ticket_messages", new_callable=AsyncMock)
    @patch("cogs.tickets.TranscriptGenerator.generate_text_transcript")
    async def test_ticket_close_with_reason(
        self, mock_gen_transcript, mock_get_msgs, mock_close, mock_get_ticket
    ):
        mock_get_ticket.return_value = self._create_mock_ticket()
        mock_get_msgs.return_value = []
        mock_gen_transcript.return_value = io.BytesIO(b"Transcript contents")

        interaction = AsyncMock()
        interaction.channel = FakeTicketThread()
        interaction.user = SimpleNamespace(
            id=12345,
            name="Alice",
            mention="<@12345>",
            display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
        )
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()

        await self.cog.ticket_close.callback(self.cog, interaction, reason="Resolved successfully")

        mock_close.assert_called_once()
        ticket_id, closing_user, reason = mock_close.call_args[0]
        self.assertEqual(ticket_id, "ticket-101")
        self.assertEqual(closing_user.username, "Alice")
        self.assertEqual(reason, "Resolved successfully")

        # Verified embed sent to thread
        interaction.channel.send.assert_called()
        # Thread archived and locked
        interaction.channel.edit.assert_called_once_with(archived=True, locked=True)

    @patch("cogs.tickets.TicketManager.get_ticket_by_thread_id", new_callable=AsyncMock)
    async def test_ticket_close_rejects_already_closed_ticket(self, mock_get_ticket):
        mock_get_ticket.return_value = self._create_mock_ticket(status=TicketStatus.CLOSED)

        interaction = AsyncMock()
        interaction.channel = FakeTicketThread()
        interaction.response = AsyncMock()
        interaction.response.send_message = AsyncMock()

        await self.cog.ticket_close.callback(self.cog, interaction, reason="Another close attempt")

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args[0][0]
        self.assertIn("already marked as closed", msg)

    @patch("cogs.tickets.TicketManager.get_ticket_by_thread_id", new_callable=AsyncMock)
    @patch("cogs.tickets.TicketManager.add_ticket_message", new_callable=AsyncMock)
    async def test_on_message_listener_syncs_thread_replies_to_firestore(
        self, mock_add_msg, mock_get_ticket
    ):
        mock_get_ticket.return_value = self._create_mock_ticket()

        # Mock incoming message in ticket thread
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock(spec=discord.Member)
        message.author.bot = False
        message.webhook_id = None
        message.author.id = 55555
        message.author.name = "StudentBob"
        message.author.display_avatar.url = "https://example.com/bob.png"
        message.author.roles = []
        message.author.guild_permissions.administrator = False
        message.channel = FakeTicketThread(thread_id=987654321)
        message.content = "Here is the screenshot of my code error."
        attachment = SimpleNamespace(url="https://cdn.discordapp.com/attachments/error.png")
        message.attachments = [attachment]
        message.created_at = datetime.now(timezone.utc)
        message.id = 11223344

        await self.cog.on_message(message)

        mock_add_msg.assert_called_once()
        ticket_id, ticket_msg = mock_add_msg.call_args[0]
        self.assertEqual(ticket_id, "ticket-101")
        self.assertEqual(ticket_msg.sender_name, "StudentBob")
        self.assertEqual(ticket_msg.sender_role, "user")
        self.assertEqual(ticket_msg.content, "Here is the screenshot of my code error.")
        self.assertEqual(ticket_msg.attachments, ["https://cdn.discordapp.com/attachments/error.png"])
        self.assertEqual(ticket_msg.source, "discord")

    @patch("cogs.tickets.TicketManager.get_ticket_by_thread_id", new_callable=AsyncMock)
    @patch("cogs.tickets.TicketManager.add_ticket_message", new_callable=AsyncMock)
    async def test_on_message_ignores_bot_or_closed_thread_messages(
        self, mock_add_msg, mock_get_ticket
    ):
        # 1. Bot message
        bot_msg = MagicMock(spec=discord.Message)
        bot_msg.author.bot = True
        await self.cog.on_message(bot_msg)
        mock_add_msg.assert_not_called()

        # 2. Message in closed ticket
        mock_get_ticket.return_value = self._create_mock_ticket(status=TicketStatus.CLOSED)
        user_msg = MagicMock(spec=discord.Message)
        user_msg.author.bot = False
        user_msg.webhook_id = None
        user_msg.channel = FakeTicketThread()
        await self.cog.on_message(user_msg)
        mock_add_msg.assert_not_called()


if __name__ == "__main__":
    unittest.main()

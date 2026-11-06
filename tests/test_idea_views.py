import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
import discord

from views.idea_views import (
    format_track_badge,
    format_difficulty_badge,
    build_idea_embed,
    SubmitIdeaModal,
    IdeaSubmissionSelectorView,
    IdeaPanelView,
    RandomIdeaRerollView,
)
from models.idea import Idea
from models.ticket import TicketUser


class IdeaViewsTestSuite(unittest.IsolatedAsyncioTestCase):
    def test_badges_formatting(self):
        self.assertEqual(format_track_badge("research"), "🔬 Research Track")
        self.assertEqual(format_track_badge("product"), "🛠️ Product Track")
        self.assertEqual(format_track_badge("kaggle"), "📊 Kaggle Track")
        self.assertEqual(format_track_badge("other"), "📦 General / Misc")

        self.assertEqual(format_difficulty_badge("beginner"), "🟢 Beginner")
        self.assertEqual(format_difficulty_badge("intermediate"), "🟡 Intermediate")
        self.assertEqual(format_difficulty_badge("advanced"), "🔴 Advanced")

    def test_build_idea_embed_structure(self):
        idea = Idea(
            id="idea-42",
            title="Neural Symbolic Reasoner",
            description="Combining formal logic with transformer embeddings.",
            track="research",
            difficulty="advanced",
            prerequisites=["Python", "Propositional Logic", "PyTorch"],
            learning_outcomes=["Theorem proving", "Embedding logic formulas"],
            rough_roadmap=["Step 1: Formal grammar", "Step 2: Training loop"],
            stats={"upvote_count": 15, "views_count": 80},
            created_by=TicketUser(discord_id="9999", username="Logician"),
        )

        embed = build_idea_embed(idea)
        self.assertIn("Neural Symbolic Reasoner", embed.title)
        self.assertIn("formal logic", embed.description)
        self.assertEqual(len(embed.fields), 6)  # Track, Diff, Engagement, Prereq, Outcomes, Roadmap

        field_names = [f.name for f in embed.fields]
        self.assertIn("Track", field_names)
        self.assertIn("Difficulty", field_names)
        self.assertIn("Engagement", field_names)
        self.assertIn("Prerequisites", field_names)
        self.assertIn("Learning Outcomes", field_names)
        self.assertIn("Rough Roadmap / Milestones", field_names)

        self.assertIn("15", [f.value for f in embed.fields if f.name == "Engagement"][0])
        self.assertIn("Logician", embed.footer.text)

    @patch("views.idea_views.IdeaManager.create_idea", new_callable=AsyncMock)
    async def test_submit_idea_modal_creates_idea(self, mock_create):
        mock_create.return_value = "idea-new-123"

        interaction = AsyncMock()
        interaction.user = SimpleNamespace(
            id=123456,
            name="AliceDev",
            display_avatar=SimpleNamespace(url="https://example.com/alice.png"),
        )
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.guild = None

        modal = SubmitIdeaModal(track="product", difficulty="intermediate")
        modal.idea_title._value = "Real-time Code Assistant"
        modal.description._value = "Low-latency inference on student laptops."
        modal.prerequisites._value = "C++\nONNX Runtime"
        modal.roadmap._value = "1. Quantization\n2. Local API"
        modal.learning_outcomes._value = "Quantization\nInference benchmarking"

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        created_idea = mock_create.call_args[0][0]
        self.assertEqual(created_idea.title, "Real-time Code Assistant")
        self.assertEqual(created_idea.track, "product")
        self.assertEqual(created_idea.difficulty, "intermediate")
        self.assertEqual(created_idea.prerequisites, ["C++", "ONNX Runtime"])
        self.assertEqual(created_idea.created_by.username, "AliceDev")
        self.assertEqual(created_idea.is_approved, False)

        interaction.followup.send.assert_called()
        self.assertIn("idea-new-123", interaction.followup.send.call_args[0][0])

    @patch("views.idea_views.IdeaManager.get_random_idea", new_callable=AsyncMock)
    async def test_idea_panel_view_random_button(self, mock_random):
        mock_random.return_value = Idea(
            id="idea-drawn",
            title="Drawn Project",
            description="A random project concept.",
            track="kaggle",
            difficulty="beginner",
        )

        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()

        view = IdeaPanelView()
        await view.random_idea_button.callback(interaction)

        mock_random.assert_called_once()
        interaction.followup.send.assert_called_once()
        embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("Drawn Project", embed.title)

    @patch("views.idea_views.IdeaManager.get_random_idea", new_callable=AsyncMock)
    async def test_idea_panel_view_empty_jar_warning(self, mock_random):
        mock_random.return_value = None

        interaction = AsyncMock()
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()

        view = IdeaPanelView()
        await view.random_idea_button.callback(interaction)

        interaction.followup.send.assert_called_once()
        self.assertIn("Idea Jar is currently empty", interaction.followup.send.call_args[0][0])


if __name__ == "__main__":
    unittest.main()

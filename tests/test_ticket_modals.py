import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from views.ticket_modals import (
    SPGModal,
    ProjectGroupRegistrationModal,
    ComputeResourceRequestModal,
    LearningResourceRequestModal,
    SupportInquiryModal,
    IdeaJarModal,
    FeedbackModal,
    ReportModal,
    MiscModal,
)
from models.ticket import TicketCategory


class TicketModalsTestSuite(unittest.IsolatedAsyncioTestCase):
    def _create_mock_interaction(self, user_id=123456789, username="StudentUser"):
        interaction = AsyncMock()
        interaction.user = SimpleNamespace(
            id=user_id,
            name=username,
            display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
        )
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    @patch("views.ticket_modals.UserManager.get_user", new_callable=AsyncMock)
    @patch("views.ticket_modals.UserManager.get_user_by_email", new_callable=AsyncMock)
    async def test_spg_modal_defaults_to_submitter_when_leader_blank(
        self, mock_get_by_email, mock_get_user, mock_create
    ):
        mock_get_user.return_value = {
            "doc_id": "uid-submitter-1",
            "full_name": "Alice Lead",
            "email": "alice@sst.scaler.com",
        }
        interaction = self._create_mock_interaction(user_id=11111, username="AliceLead")

        modal = ProjectGroupRegistrationModal()
        modal.project_name._value = "Autonomous Drone Fleet"
        modal.track._value = "Research"
        modal.team_leader._value = ""  # Left blank by student!
        modal.team_members._value = "bob@sst.scaler.com\ncarol@sst.scaler.com"
        modal.duration_and_frequency._value = "60, 14"

        # Mock member email resolution
        def email_resolver(email):
            if "bob" in email:
                return {"doc_id": "uid-bob-2", "full_name": "Bob Iyer"}
            if "carol" in email:
                return {"doc_id": "uid-carol-3", "full_name": "Carol Das"}
            return None

        mock_get_by_email.side_effect = email_resolver

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        self.assertEqual(kwargs["category"], TicketCategory.SPG_REGISTRATION)
        self.assertIn("SPG: Autonomous Drone Fleet", kwargs["title"])

        fields = kwargs["fields"]
        self.assertEqual(fields["leader_uid"], "uid-submitter-1")
        self.assertIn("Alice Lead", fields["Team Leader"])
        self.assertEqual(fields["member_uids"], ["uid-bob-2", "uid-carol-3"])
        self.assertEqual(fields["duration_days"], 60)
        self.assertEqual(fields["frequency_days"], 14)
        self.assertEqual(fields["Group Type"], "Project Group")

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    @patch("views.ticket_modals.UserManager.get_user", new_callable=AsyncMock)
    @patch("views.ticket_modals.UserManager.get_user_by_email", new_callable=AsyncMock)
    async def test_spg_modal_resolves_leader_email_and_mention(
        self, mock_get_by_email, mock_get_user, mock_create
    ):
        mock_get_by_email.return_value = {
            "doc_id": "uid-external-lead",
            "full_name": "David Lead",
            "email": "david@sst.scaler.com",
        }
        interaction = self._create_mock_interaction()

        modal = ProjectGroupRegistrationModal()
        modal.project_name._value = "Vision Pipeline"
        modal.track._value = "Product"
        modal.team_leader._value = "david@sst.scaler.com"
        modal.team_members._value = ""
        modal.duration_and_frequency._value = "90 / 21"

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        fields = mock_create.call_args[1]["fields"]
        self.assertEqual(fields["leader_uid"], "uid-external-lead")
        self.assertIn("David Lead", fields["Team Leader"])
        self.assertEqual(fields["duration_days"], 90)
        self.assertEqual(fields["frequency_days"], 21)

    async def test_spg_modal_rejects_more_than_six_members(self):
        interaction = self._create_mock_interaction()
        modal = ProjectGroupRegistrationModal()
        modal.project_name._value = "Giant Team"
        modal.track._value = "Kaggle"
        modal.team_leader._value = "lead-uid"
        modal.team_members._value = "\n".join([f"member-{i}" for i in range(1, 8)])
        modal.duration_and_frequency._value = "60, 14"

        await modal.on_submit(interaction)

        interaction.followup.send.assert_called_once()
        call_msg = interaction.followup.send.call_args[0][0]
        self.assertIn("Maximum 6 team members allowed", call_msg)

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    async def test_compute_resource_modal_field_mapping(self, mock_create):
        interaction = self._create_mock_interaction()
        modal = ComputeResourceRequestModal()
        modal.project_name._value = "Project Alpha"
        modal.resources_needed._value = "4x A100 GPUs for fine-tuning"
        modal.progress_proof._value = "https://github.com/reinforce/alpha"
        modal.justification._value = "Evaluating llama-3 on domain dataset."

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        fields = mock_create.call_args[1]["fields"]
        self.assertEqual(fields["SPG Name"], "Project Alpha")
        self.assertEqual(fields["Resources Requested"], "4x A100 GPUs for fine-tuning")
        self.assertEqual(fields["Progress Proof"], "https://github.com/reinforce/alpha")
        self.assertEqual(fields["Justification"], "Evaluating llama-3 on domain dataset.")

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    async def test_learning_resource_modal_field_mapping(self, mock_create):
        interaction = self._create_mock_interaction()
        modal = LearningResourceRequestModal()
        modal.topic._value = "Graph Neural Networks"
        modal.resource_format._value = "Curated Roadmap & Video Lectures"
        modal.target_audience._value = "Research Track"
        modal.description._value = "Needs PyG examples and paper links."

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        fields = mock_create.call_args[1]["fields"]
        self.assertEqual(fields["Topic / Subject Area"], "Graph Neural Networks")
        self.assertEqual(fields["Resource Format"], "Curated Roadmap & Video Lectures")
        self.assertEqual(fields["Target Audience / Track"], "Research Track")
        self.assertEqual(fields["Description & Suggested Links"], "Needs PyG examples and paper links.")

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    async def test_support_inquiry_modal_field_mapping(self, mock_create):
        interaction = self._create_mock_interaction()
        modal = SupportInquiryModal()
        modal.subject._value = "Datathon Timeline Question"
        modal.details._value = "When will the baseline code be released?"

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        fields = mock_create.call_args[1]["fields"]
        self.assertEqual(fields["Subject"], "Datathon Timeline Question")
        self.assertEqual(fields["Details"], "When will the baseline code be released?")

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    async def test_idea_jar_modal_metadata_parsing(self, mock_create):
        interaction = self._create_mock_interaction()
        modal = IdeaJarModal()
        modal.idea_title._value = "RL Robot Arm Controller (Research / Advanced)"
        modal.overview._value = "PPO simulation for robotic arm manipulation."
        modal.prerequisites._value = "Python\nPyTorch\nMuJoCo"
        modal.roadmap._value = "Phase 1: Sim environment\nPhase 2: Training PPO"
        modal.learning_outcomes._value = "Continuous control\nPolicy gradients"

        await modal.on_submit(interaction)

        mock_create.assert_called_once()
        fields = mock_create.call_args[1]["fields"]
        self.assertEqual(fields["Idea Title"], "RL Robot Arm Controller")
        self.assertEqual(fields["track"], "research")
        self.assertEqual(fields["difficulty"], "advanced")
        self.assertEqual(fields["prerequisites"], ["Python", "PyTorch", "MuJoCo"])
        self.assertEqual(fields["learning_outcomes"], ["Continuous control", "Policy gradients"])

    @patch("views.ticket_modals.create_ticket_thread_and_doc", new_callable=AsyncMock)
    async def test_feedback_and_report_modal_field_mapping(self, mock_create):
        interaction = self._create_mock_interaction()

        # Feedback
        fb_modal = FeedbackModal()
        fb_modal.topic._value = "Hackathon Judging Criteria"
        fb_modal.comments._value = "Provide rubric in advance."
        await fb_modal.on_submit(interaction)

        fields_fb = mock_create.call_args[1]["fields"]
        self.assertEqual(fields_fb["Feedback Topic"], "Hackathon Judging Criteria")
        self.assertEqual(fields_fb["Feedback Details"], "Provide rubric in advance.")

        # Confidential Report
        mock_create.reset_mock()
        report_modal = ReportModal()
        report_modal.summary._value = "Unfair team behavior"
        report_modal.description._value = "Specific details of misconduct."
        await report_modal.on_submit(interaction)

        fields_rep = mock_create.call_args[1]["fields"]
        self.assertEqual(fields_rep["Incident Summary"], "Unfair team behavior")
        self.assertEqual(fields_rep["Report Details"], "Specific details of misconduct.")


if __name__ == "__main__":
    unittest.main()

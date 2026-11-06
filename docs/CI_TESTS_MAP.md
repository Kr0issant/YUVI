# YUVI Discord Bot - CI/CD Test Suite & Coverage Map

This document provides a single-source-of-truth inventory of the test suites running in CI/CD for the **YUVI Discord Bot & Bridge**, mapping every test module to the subsystems, commands, endpoints, and architectural guarantees it verifies.

---

## 1. Running the Test Suites

### Unit & Regression Suite
```bash
uv run python -m unittest discover -s tests -v
# Or via pytest:
uv run pytest -v
```

### Static Syntax & Compilation Validation
```bash
uv run python -m compileall -q cogs utils server.py views models
```

---

## 2. Architecture & Mocking Strategy

The YUVI test suite runs fully isolated from external network dependencies:
- **Discord Gateway Isolation**: Tests simulate `discord.Interaction`, `discord.Thread`, and `discord.Message` objects using mock hierarchies (`AsyncMock` and `MagicMock`). No live Discord bot token or gateway connection is required.
- **Firestore Isolation**: Database queries and documents are mocked through test fakes, ensuring tests run in sub-second execution times with 0 external Google Cloud dependencies.

---

## 3. Test Suite Inventory (`tests/`)

The YUVI test suite consists of 8 comprehensive test modules covering all bot commands, views, modals, server endpoints, and utility managers:

| Test Module | Subsystem / Area | Focus & Scenarios Verified |
| :--- | :--- | :--- |
| **`test_ticket_modals.py`** | Ticket Modals (`views/ticket_modals.py`) | Tests all Discord ticket creation modals: `ProjectGroupRegistrationModal` defaults to submitter when leader is blank, resolves leader emails/mentions to canonical user UIDs without asking students for Firebase UIDs, caps team members at 6, parses duration/frequency, and generates synchronized human & machine field dictionaries matching web dashboard contracts; validates `ComputeResourceRequestModal`, `LearningResourceRequestModal`, `SupportInquiryModal`, `IdeaJarModal`, `FeedbackModal`, and `ReportModal`. |
| **`test_ticket_lifecycle.py`** | Ticket Commands & Sync (`cogs/tickets.py` & `views/ticket_controls.py`) | Tests ticket cog commands and thread synchronization: `/setup-tickets` deploying official category panel; `/ticket close` permission enforcement, closing notes, and automatic thread archiving/locking; and the `on_message` listener syncing thread conversations to Firestore with user/lead/admin role resolution and attachment capture while ignoring bot/webhook/closed thread events. |
| **`test_idea_views.py`** | Idea Jar Views & Commands (`views/idea_views.py` & `cogs/ideas.py`) | Tests Idea Jar embeds and interactive views: `format_track_badge` and `format_difficulty_badge`; `build_idea_embed` layout; `SubmitIdeaModal` parsing title metadata, prerequisites, and roadmap; `IdeaView` upvote button interaction with duplicate vote prevention; and `/random_idea` panel reroll. |
| **`test_user_manager.py`** | User & Identity Management (`utils/user_manager.py`) | Tests `UserManager` operations: resolving users by Discord ID via verified link tokens, email queries, unlinking Discord accounts from Firestore, and multi-layered verification checks (guild administrator permission, role ID whitelist, role name whitelist, and Firestore fallback). |
| **`test_bridge.py`** | FastAPI Bridge (`server.py`) | Tests FastAPI server bridge endpoints: `/tickets/create-thread` with internal secret verification, spawning private threads with initial messages and control buttons; `/tickets/relay-message` relaying web replies into Discord threads; and Firestore idea/ticket queries. |
| **`test_verification_webhook.py`** | Verification Webhook (`server.py`) | Tests `/verify-success` webhook: internal secret verification, role assignment idempotency, orientation kickoff role toggle (`ENABLE_KICKOFF_ROLE`), and full name nickname synchronization (`ENABLE_NICKNAME_SYNC`). |
| **`test_discord_queue.py`** | Queue & Rate Limiter (`utils/discord_queue.py`) | Tests `DiscordQueueManager`: task prioritization, rate limit backoff handling, retry policies, and serial execution guarantees. |
| **`test_auth_links.py`** | One-Time Auth Links (`utils/auth_links.py`) | Tests cryptographic token generation (`create_auth_token`), expiration timestamps, and one-time verification link redemption. |

---

## 4. CI Pipeline Definition

Defined in `.github/workflows/ci.yml`:
- **Python Version**: 3.13+ managed via `astral-sh/setup-uv`
- **Steps**:
  1. `uv sync --locked`
  2. `uv run python -m unittest discover -s tests -v`
  3. `uv run python -m compileall -q cogs utils server.py views models`

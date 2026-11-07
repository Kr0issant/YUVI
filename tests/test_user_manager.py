import os
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import discord

from utils.user_manager import UserManager


class FakeUserDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.reference = MagicMock()

    @property
    def exists(self):
        return True

    def to_dict(self):
        return dict(self._data)


class UserManagerTestSuite(unittest.IsolatedAsyncioTestCase):
    @patch("utils.user_manager.verified_uid_for_discord")
    @patch.object(UserManager, "_get_db")
    async def test_get_user_with_verified_link(self, mock_get_db, mock_verified_uid):
        mock_verified_uid.return_value = "uid-100"
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        fake_doc = FakeUserDoc("uid-100", {"id": "uid-100", "full_name": "Alice Lead", "email": "alice@sst.scaler.com"})
        mock_db.collection.return_value.document.return_value.get.return_value = fake_doc

        user = await UserManager.get_user("123456789")
        self.assertIsNotNone(user)
        self.assertEqual(user["doc_id"], "uid-100")
        self.assertEqual(user["full_name"], "Alice Lead")

    @patch("utils.user_manager.verified_uid_for_discord")
    @patch.object(UserManager, "_get_db")
    async def test_get_user_returns_none_when_unlinked(self, mock_get_db, mock_verified_uid):
        mock_verified_uid.return_value = None
        user = await UserManager.get_user("999999999")
        self.assertIsNone(user)

    @patch.object(UserManager, "_get_db")
    async def test_get_user_by_email(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        fake_doc = FakeUserDoc("uid-bob", {"id": "uid-bob", "full_name": "Bob Student", "email": "bob@sst.scaler.com"})
        mock_db.collection.return_value.where.return_value.stream.return_value = [fake_doc]

        user = await UserManager.get_user_by_email("bob@sst.scaler.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["doc_id"], "uid-bob")
        self.assertEqual(user["full_name"], "Bob Student")

    @patch.object(UserManager, "_get_db")
    async def test_unlink_user_clears_firestore_fields(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        fake_doc = FakeUserDoc("uid-charlie", {"id": "uid-charlie", "discord_id": "12345"})
        mock_db.collection.return_value.where.return_value.stream.return_value = [fake_doc]
        mock_db.collection.return_value.document.return_value.get.return_value.exists = False

        res = await UserManager.unlink_user("12345")
        self.assertTrue(res)
        fake_doc.reference.update.assert_called()
        update_payload = fake_doc.reference.update.call_args[0][0]
        self.assertIsNone(update_payload["discord_id"])
        self.assertEqual(update_payload["is_verified"], False)

    async def test_is_user_verified_by_administrator_permission(self):
        user = SimpleNamespace(
            id=111,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=True),
        )
        self.assertTrue(await UserManager.is_user_verified(user))

    async def test_is_user_verified_by_role_name(self):
        role_verified = SimpleNamespace(id=999, name="Verified Member")
        user = SimpleNamespace(
            id=222,
            roles=[role_verified],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        self.assertTrue(await UserManager.is_user_verified(user))

    @patch("utils.user_manager.verified_uid_for_discord")
    @patch.object(UserManager, "_get_db")
    async def test_is_user_verified_falls_back_to_firestore(self, mock_get_db, mock_verified_uid):
        mock_verified_uid.return_value = "uid-firestore"
        mock_get_db.return_value = MagicMock()

        user = SimpleNamespace(
            id=333,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        self.assertTrue(await UserManager.is_user_verified(user))

    @patch("utils.user_manager.verified_uid_for_discord")
    @patch.object(UserManager, "_get_db")
    async def test_is_user_verified_returns_false_when_unlinked_and_noroles(self, mock_get_db, mock_verified_uid):
        mock_verified_uid.return_value = None
        mock_get_db.return_value = MagicMock()

        user = SimpleNamespace(
            id=444,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        self.assertFalse(await UserManager.is_user_verified(user))

    async def test_is_user_admin_by_administrator_permission(self):
        user = SimpleNamespace(
            id=111,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=True),
        )
        self.assertTrue(await UserManager.is_user_admin(user))

    async def test_is_user_admin_by_role_id(self):
        role_admin = SimpleNamespace(id=12345, name="SomeRole")
        user = SimpleNamespace(
            id=222,
            roles=[role_admin],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        with patch.dict(os.environ, {"ADMIN_ROLE_ID": "12345"}):
            self.assertTrue(await UserManager.is_user_admin(user))

    async def test_is_user_admin_by_role_name(self):
        role_admin = SimpleNamespace(id=999, name="Admin")
        user = SimpleNamespace(
            id=222,
            roles=[role_admin],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        self.assertTrue(await UserManager.is_user_admin(user))

    @patch.object(UserManager, "get_user")
    async def test_is_user_admin_by_firestore_doc(self, mock_get_user):
        mock_get_user.return_value = {"is_admin": True}
        user = SimpleNamespace(
            id=333,
            roles=[],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        self.assertTrue(await UserManager.is_user_admin(user))

    @patch.object(UserManager, "get_user")
    async def test_is_user_admin_returns_false_for_regular_user(self, mock_get_user):
        mock_get_user.return_value = {"is_admin": False, "role": "member"}
        user = SimpleNamespace(
            id=444,
            roles=[SimpleNamespace(id=888, name="Student")],
            guild_permissions=SimpleNamespace(administrator=False),
        )
        self.assertFalse(await UserManager.is_user_admin(user))


if __name__ == "__main__":
    unittest.main()

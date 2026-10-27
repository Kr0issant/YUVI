import os
import asyncio
from typing import Any, Dict, Optional, Union
from firebase_admin import firestore
from utils.auth_links import verified_uid_for_discord
from utils.firestore_client import get_firestore_client

USERS_COLLECTION = "users"


class UserManager:
    @staticmethod
    def _get_db():
        return get_firestore_client()

    @classmethod
    async def get_user(cls, discord_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the canonical profile for a proven Discord link."""
        clean_id = str(discord_id).strip()

        def _sync_get():
            try:
                db = cls._get_db()
                uid = verified_uid_for_discord(db, clean_id)
                if not uid:
                    return None
                doc = db.collection(USERS_COLLECTION).document(uid).get()
                if not doc.exists:
                    return None
                return {**(doc.to_dict() or {}), "doc_id": doc.id}
            except Exception as e:
                print(f"[UserManager] Firestore query error fetching user {discord_id}: {e}")
                return None

        return await asyncio.to_thread(_sync_get)

    @classmethod
    async def get_user_by_email(cls, email: str) -> Optional[Dict[str, Any]]:
        """Query the canonical profile by email, ignoring stale aliases."""
        clean_email = str(email).lower().strip()

        def _sync_query():
            try:
                db = cls._get_db()
                docs = db.collection(USERS_COLLECTION).where("email", "==", clean_email).stream()
                matches = [
                    {**data, "doc_id": doc.id}
                    for doc in docs
                    if (data := doc.to_dict() or {}).get("id") == doc.id
                ]
                return matches[0] if len(matches) == 1 else None
            except Exception as e:
                print(f"[UserManager] Firestore query error querying email {email}: {e}")
                return None

        return await asyncio.to_thread(_sync_query)

    @classmethod
    async def unlink_user(cls, discord_id: str) -> bool:
        """Unlink Discord ID from user record in Firestore and clear verification status."""
        def _sync_unlink():
            try:
                db = cls._get_db()
                clean_id = str(discord_id).strip()
                unlinked = False

                query_str = db.collection(USERS_COLLECTION).where("discord_id", "==", clean_id)
                for doc in query_str.stream():
                    doc.reference.update({
                        "discord_id": None,
                        "is_verified": False,
                        "discord_link_version": None,
                        "verified_at": None,
                        "social_links.discord": None,
                        "updated_at": firestore.SERVER_TIMESTAMP
                    })
                    unlinked = True

                if clean_id.isdigit():
                    query_int = db.collection(USERS_COLLECTION).where("discord_id", "==", int(clean_id))
                    for doc in query_int.stream():
                        doc.reference.update({
                            "discord_id": None,
                            "is_verified": False,
                            "discord_link_version": None,
                            "verified_at": None,
                            "social_links.discord": None,
                            "updated_at": firestore.SERVER_TIMESTAMP
                        })
                        unlinked = True

                direct_doc = db.collection(USERS_COLLECTION).document(clean_id)
                if direct_doc.get().exists:
                    direct_doc.delete()
                    unlinked = True

                return unlinked
            except Exception as e:
                print(f"[UserManager] Error unlinking user {discord_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_unlink)

    @classmethod
    async def is_user_verified(
        cls,
        user: Any,
        guild: Optional[Any] = None
    ) -> bool:
        """Check whether a user is verified via Discord roles or linked in Firestore."""
        # 1. Check roles if user is a Member or can be resolved as a Member
        member = user if hasattr(user, "roles") else (guild.get_member(user.id) if guild and hasattr(guild, "get_member") else None)

        if member:
            # Administrators are always authorized
            permissions = getattr(member, "guild_permissions", None)
            if permissions and getattr(permissions, "administrator", False):
                return True

            role_ids = {str(getattr(r, "id", "")) for r in getattr(member, "roles", [])}
            verified_role_id = os.getenv("VERIFIED_ROLE_ID")
            admin_role_id = os.getenv("ADMIN_ROLE_ID")
            support_role_id = os.getenv("SUPPORT_ROLE_ID")

            for rid in (verified_role_id, admin_role_id, support_role_id):
                if rid and str(rid).strip() in role_ids:
                    return True

            for r in getattr(member, "roles", []):
                if getattr(r, "name", "").lower() in ("verified member", "verified", "member", "admin", "lead"):
                    return True

        # 2. Check Firestore canonical link
        def _sync_check():
            try:
                db = cls._get_db()
                return bool(verified_uid_for_discord(db, str(getattr(user, "id", user))))
            except Exception as e:
                print(f"[UserManager] Error checking verification in Firestore for {getattr(user, 'id', user)}: {e}")
                return False

        return await asyncio.to_thread(_sync_check)

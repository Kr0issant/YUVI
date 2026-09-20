import asyncio
from typing import Any, Dict, Optional
from utils.firestore_client import get_firestore_client

USERS_COLLECTION = "users"

class UserManager:
    @staticmethod
    def _get_db():
        return get_firestore_client()

    @classmethod
    async def get_user(cls, discord_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user record from Firestore by Discord ID (doc ID or field)."""
        def _sync_get():
            try:
                db = cls._get_db()
                # 1. Direct document lookup by discord_id
                doc = db.collection(USERS_COLLECTION).document(str(discord_id)).get()
                if doc.exists:
                    data = doc.to_dict()
                    data["doc_id"] = doc.id
                    return data

                # 2. Query by discord_id field (if doc_id is Firebase UID or email)
                query = db.collection(USERS_COLLECTION).where("discord_id", "==", str(discord_id)).limit(1)
                docs = list(query.stream())
                if docs:
                    data = docs[0].to_dict()
                    data["doc_id"] = docs[0].id
                    return data

                return None
            except Exception as e:
                print(f"[UserManager] Error fetching user {discord_id}: {e}")
                return None

        return await asyncio.to_thread(_sync_get)

    @classmethod
    async def get_user_by_email(cls, email: str) -> Optional[Dict[str, Any]]:
        """Query user record from Firestore by email."""
        def _sync_query():
            try:
                db = cls._get_db()
                query = db.collection(USERS_COLLECTION).where("email", "==", str(email).lower().strip()).limit(1)
                docs = list(query.stream())
                if docs:
                    data = docs[0].to_dict()
                    data["doc_id"] = docs[0].id
                    return data
                return None
            except Exception as e:
                print(f"[UserManager] Error querying user by email {email}: {e}")
                return None

        return await asyncio.to_thread(_sync_query)

    @classmethod
    async def unlink_user(cls, discord_id: str) -> bool:
        """Unlink Discord ID from user record in Firestore."""
        def _sync_delete():
            try:
                db = cls._get_db()
                # Check direct doc
                doc_ref = db.collection(USERS_COLLECTION).document(str(discord_id))
                if doc_ref.get().exists:
                    doc_ref.delete()
                    return True

                # Check query by field
                query = db.collection(USERS_COLLECTION).where("discord_id", "==", str(discord_id)).limit(1)
                docs = list(query.stream())
                if docs:
                    # Clear discord_id from the user profile or delete
                    docs[0].reference.update({"discord_id": None})
                    return True

                return False
            except Exception as e:
                print(f"[UserManager] Error unlinking user {discord_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_delete)

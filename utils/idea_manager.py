import asyncio
import random
from typing import Any, Dict, List, Optional
from firebase_admin import firestore
from models.idea import Idea
from models.ticket import TicketUser
from utils.firestore_client import get_firestore_client

IDEAS_COLLECTION = "ideas"

class IdeaManager:
    @staticmethod
    def _get_db():
        return get_firestore_client()

    @classmethod
    async def create_idea(cls, idea: Idea) -> str:
        """Create a new idea in Firestore with an auto-generated ID."""
        def _sync_create():
            try:
                db = cls._get_db()
                doc_ref = db.collection(IDEAS_COLLECTION).document()
                idea.id = doc_ref.id
                doc_ref.set(idea.to_dict())
                print(f"[IdeaManager] Created idea {doc_ref.id} (Approved: {idea.is_approved})")
                return doc_ref.id
            except Exception as e:
                print(f"[IdeaManager] Error creating idea: {e}")
                raise e

        return await asyncio.to_thread(_sync_create)

    @classmethod
    async def get_idea(cls, idea_id: str) -> Optional[Idea]:
        """Fetch an idea by its Firestore document ID."""
        def _sync_get():
            try:
                db = cls._get_db()
                doc = db.collection(IDEAS_COLLECTION).document(idea_id.strip()).get()
                if doc.exists:
                    return Idea.from_dict(doc.id, doc.to_dict())
                return None
            except Exception as e:
                print(f"[IdeaManager] Error getting idea {idea_id}: {e}")
                return None

        return await asyncio.to_thread(_sync_get)

    @classmethod
    async def get_random_idea(
        cls,
        track: Optional[str] = None,
        difficulty: Optional[str] = None
    ) -> Optional[Idea]:
        """Fetch a random approved idea, with optional track or difficulty filters."""
        def _sync_random():
            try:
                db = cls._get_db()
                query = db.collection(IDEAS_COLLECTION).where("is_approved", "==", True)
                if track:
                    query = query.where("track", "==", track.lower().strip())
                if difficulty:
                    query = query.where("difficulty", "==", difficulty.lower().strip())

                docs = list(query.stream())
                if not docs:
                    return None

                selected_doc = random.choice(docs)
                return Idea.from_dict(selected_doc.id, selected_doc.to_dict())
            except Exception as e:
                print(f"[IdeaManager] Error fetching random idea: {e}")
                return None

        return await asyncio.to_thread(_sync_random)

    @classmethod
    async def list_ideas(
        cls,
        is_approved: Optional[bool] = True,
        track: Optional[str] = None,
        limit: int = 50
    ) -> List[Idea]:
        """List ideas with optional approval and track filters."""
        def _sync_list():
            try:
                db = cls._get_db()
                query = db.collection(IDEAS_COLLECTION)
                if is_approved is not None:
                    query = query.where("is_approved", "==", is_approved)
                if track:
                    query = query.where("track", "==", track.lower().strip())

                docs = list(query.limit(limit).stream())
                return [Idea.from_dict(d.id, d.to_dict()) for d in docs]
            except Exception as e:
                print(f"[IdeaManager] Error listing ideas: {e}")
                return []

        return await asyncio.to_thread(_sync_list)

    @classmethod
    async def approve_idea(cls, idea_id: str, admin: TicketUser) -> bool:
        """Mark an idea as approved."""
        def _sync_approve():
            try:
                db = cls._get_db()
                doc_ref = db.collection(IDEAS_COLLECTION).document(idea_id.strip())
                if not doc_ref.get().exists:
                    return False
                doc_ref.update({
                    "is_approved": True,
                    "approved_by": admin.to_dict(),
                    "approved_at": firestore.SERVER_TIMESTAMP
                })
                print(f"[IdeaManager] Approved idea {idea_id} by {admin.username}")
                return True
            except Exception as e:
                print(f"[IdeaManager] Error approving idea {idea_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_approve)

    @classmethod
    async def delete_idea(cls, idea_id: str) -> bool:
        """Delete an idea document."""
        def _sync_delete():
            try:
                db = cls._get_db()
                db.collection(IDEAS_COLLECTION).document(idea_id.strip()).delete()
                print(f"[IdeaManager] Deleted idea {idea_id}")
                return True
            except Exception as e:
                print(f"[IdeaManager] Error deleting idea {idea_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_delete)

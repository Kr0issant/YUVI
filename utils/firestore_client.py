import firebase_admin
from firebase_admin import credentials, firestore
import os

_db = None

def get_firestore_client() -> firestore.firestore.Client:
    global _db
    if _db is not None:
        return _db
    
    if not firebase_admin._apps:
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
            
    _db = firestore.client()
    return _db

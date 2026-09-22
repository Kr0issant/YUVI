import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

_db = None

def get_firestore_client() -> firestore.firestore.Client:
    global _db
    if _db is not None:
        return _db
    
    if not firebase_admin._apps:
        # 1. Check if JSON string is provided in environment variable (Render / Cloud deployment)
        raw_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or os.getenv("FIREBASE_CREDENTIALS_JSON")
        if raw_json and raw_json.strip():
            try:
                cred_dict = json.loads(raw_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                print("[FirestoreClient] Initialized Firebase via FIREBASE_SERVICE_ACCOUNT_JSON environment variable.")
            except Exception as e:
                print(f"[FirestoreClient] Error parsing FIREBASE_SERVICE_ACCOUNT_JSON: {e}")

        # 2. Check path from GOOGLE_APPLICATION_CREDENTIALS or local serviceAccountKey.json
        if not firebase_admin._apps:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                print(f"[FirestoreClient] Initialized Firebase via file path: {cred_path}")
            else:
                print(f"[FirestoreClient] WARNING: '{cred_path}' not found. Attempting Application Default Credentials...")
                firebase_admin.initialize_app()
            
    _db = firestore.client()
    return _db

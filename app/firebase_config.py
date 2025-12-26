import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

def init_firebase():
    # Si Firebase est déjà initialisé, on renvoie les instances existantes
    if firebase_admin._apps:
        return firestore.client(), storage.bucket()

    # 1. On cherche la clé secrète dans les variables d'environnement (Dokploy)
    service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    storage_bucket = os.environ.get('VITE_FIREBASE_STORAGE_BUCKET', 'solufuse-5647c.firebasestorage.app')

    if service_account_json:
        try:
            # On nettoie la chaîne si elle contient des retours à la ligne bizarres
            if isinstance(service_account_json, str):
                service_account_dict = json.loads(service_account_json)
            else:
                service_account_dict = service_account_json
                
            cred = credentials.Certificate(service_account_dict)
            firebase_admin.initialize_app(cred, {
                'storageBucket': storage_bucket
            })
            print("✅ Firebase Admin initialisé avec SERVICE ACCOUNT (Production)")
        except Exception as e:
            print(f"❌ Erreur lecture SERVICE ACCOUNT: {str(e)}")
            # Fallback en mode développement (si local)
            firebase_admin.initialize_app(credentials.ApplicationDefault())
    else:
        print("⚠️ Pas de SERVICE ACCOUNT détecté, tentative avec ApplicationDefault...")
        firebase_admin.initialize_app()

    return firestore.client(), storage.bucket()

# Instances globales
db, bucket = init_firebase()

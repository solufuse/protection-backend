import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

db = None
bucket = None

# NOM DU BUCKET EN DUR (Pour être sûr à 100%)
BUCKET_NAME = "solufuse-5647c.firebasestorage.app"

def init_firebase():
    global db, bucket
    
    if firebase_admin._apps:
        return firestore.client(), storage.bucket(BUCKET_NAME)

    print("🔥 Initialisation Firebase...")
    
    # 1. Récupération de la clé Service Account
    service_account_raw = os.environ.get('FIREBASE_SERVICE_ACCOUNT')

    if not service_account_raw:
        print("⚠️ ERREUR: Variable FIREBASE_SERVICE_ACCOUNT manquante.")
        return None, None

    try:
        # Nettoyage de la clé (suppression des guillemets potentiels ajoutés par Dokploy)
        clean_json = service_account_raw.strip()
        if clean_json.startswith("'") and clean_json.endswith("'"):
            clean_json = clean_json[1:-1]
        
        service_account_dict = json.loads(clean_json)
        
        # 2. Initialisation App
        cred = credentials.Certificate(service_account_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': BUCKET_NAME
        })
        
        # 3. Connexion Services
        db = firestore.client()
        # On force le nom du bucket ici aussi pour éviter l'erreur "Bucket name not specified"
        bucket = storage.bucket(BUCKET_NAME)
        
        print(f"✅ Firebase connecté ! (Bucket: {BUCKET_NAME})")
        return db, bucket

    except Exception as e:
        print(f"❌ ERREUR INIT FIREBASE: {str(e)}")
        # On relance l'erreur pour voir le traceback si besoin, 
        # ou on return None si on veut que le serveur démarre quand même (mode dégradé)
        return None, None

# Lancement immédiat
try:
    db, bucket = init_firebase()
except Exception as e:
    print(f"⚠️ Erreur globale: {e}")

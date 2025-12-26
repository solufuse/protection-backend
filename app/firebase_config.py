import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

db = None
bucket = None

def init_firebase():
    global db, bucket
    
    # Éviter la double initialisation
    if firebase_admin._apps:
        return firestore.client(), storage.bucket()

    print("🔥 Démarrage initialisation Firebase...")
    
    service_account_raw = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    storage_bucket = os.environ.get('VITE_FIREBASE_STORAGE_BUCKET', 'solufuse-5647c.firebasestorage.app')

    if not service_account_raw:
        print("⚠️ ATTENTION: Variable FIREBASE_SERVICE_ACCOUNT vide ou introuvable.")
        return None, None

    try:
        # Tentative de nettoyage du JSON (parfois Dokploy ajoute des guillemets autour)
        clean_json = service_account_raw.strip()
        if clean_json.startswith("'") and clean_json.endswith("'"):
            clean_json = clean_json[1:-1]
        
        service_account_dict = json.loads(clean_json)
        
        cred = credentials.Certificate(service_account_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': storage_bucket
        })
        
        db = firestore.client()
        bucket = storage.bucket()
        print("✅ Firebase connecté avec succès !")
        return db, bucket

    except json.JSONDecodeError as e:
        print(f"❌ ERREUR JSON: La clé FIREBASE_SERVICE_ACCOUNT est mal formatée. {str(e)}")
        print(f"   Contenu reçu (début): {service_account_raw[:50]}...")
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE FIREBASE: {str(e)}")
    
    return None, None

# On lance l'init mais on ne fait PAS planter l'app si ça échoue
try:
    db, bucket = init_firebase()
except Exception as e:
    print(f"⚠️ Erreur globale init: {e}")

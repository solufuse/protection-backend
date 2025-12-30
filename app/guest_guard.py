
import os
from fastapi import HTTPException

BASE_STORAGE = "/app/storage"

def get_user_storage(uid: str):
    # Stockage unifié : tout le monde au même endroit
    path = os.path.join(BASE_STORAGE, uid)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def check_guest_restrictions(uid: str, is_guest: bool, action: str):
    """
    Centralise toute la politique de restriction Guest.
    """
    user_path = get_user_storage(uid)

    # Si c'est un membre payant/inscrit, aucune limite.
    if not is_guest:
        return user_path

    # --- RÈGLES POUR INVITÉS (GUESTS) ---
    
    # Règle 1 : Interdiction formelle de créer des projets (dossiers)
    if action == "create_project":
        raise HTTPException(
            status_code=403, 
            detail="🔒 CREATION REFUSÉE : Les invités ne peuvent pas créer de projets. Connectez-vous !"
        )

    # Règle 2 : Quota strict de 5 fichiers
    if action == "upload":
        # On compte les fichiers existants
        files = [f for f in os.listdir(user_path) if os.path.isfile(os.path.join(user_path, f))]
        if len(files) >= 5:
            raise HTTPException(
                status_code=403, 
                detail="🔒 QUOTA ATTEINT : Mode démo limité à 5 fichiers. Connectez-vous pour continuer."
            )
            
    return user_path

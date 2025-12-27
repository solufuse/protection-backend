import jwt

def get_uid_from_token(token: str) -> str:
    """
    Décode le token JWT (sans vérification de signature ici pour rapidité/compatibilité, 
    ou avec vérification si la clé est dispo) pour extraire l'UID (sub).
    Pour Firebase/Google Auth, l'ID est dans 'sub' ou 'user_id'.
    """
    try:
        # On décode sans vérifier la signature pour récupérer le payload
        # (Dans un env prod strict, on vérifierait la signature avec les clés publiques Google)
        decoded = jwt.get_unverified_header(token)
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # Firebase met l'UID dans 'user_id' ou 'sub'
        return payload.get("user_id") or payload.get("sub")
    except Exception as e:
        print(f"Token decoding error: {e}")
        # Si échec (ex: c'est déjà un UID ou token invalide), on retourne le token tel quel 
        # au cas où c'était déjà l'ID (fallback)
        return token

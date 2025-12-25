import re

def parse_technical_text(text: str) -> dict:
    """
    Analyse un texte technique pour extraire :
    - Puissance (normalisée en kVA)
    - Tension (normalisée en kV)
    - Courant (normalisé en A)
    """
    
    # Nettoyage basique
    text = text.replace(',', '.') # Gestion des virgules françaises
    
    extracted = {
        "raw_text": text,
        "power_kva": None,
        "voltage_kv": None,
        "current_a": None,
        "detected_type": "UNKNOWN"
    }

    # --- 1. DETECTION PUISSANCE (MVA, kVA, MW) ---
    # Regex: Cherche un nombre suivi de MVA, kVA ou MW
    # Ex: "63 MVA", "1000kVA", "2.5 MW"
    
    # MVA -> kVA
    match_mva = re.search(r'(\d+(?:\.\d+)?)\s*(?:MVA|MW)', text, re.IGNORECASE)
    if match_mva:
        val = float(match_mva.group(1))
        extracted["power_kva"] = val * 1000.0 # Conversion en kVA
        extracted["detected_type"] = "TRANSFORMER" # Probablement un transfo

    # kVA -> kVA
    if not match_mva:
        match_kva = re.search(r'(\d+(?:\.\d+)?)\s*kVA', text, re.IGNORECASE)
        if match_kva:
            extracted["power_kva"] = float(match_kva.group(1))
            extracted["detected_type"] = "TRANSFORMER"

    # --- 2. DETECTION TENSION (kV, V) ---
    # kV -> kV
    match_kv = re.search(r'(\d+(?:\.\d+)?)\s*kV', text, re.IGNORECASE)
    if match_kv:
        extracted["voltage_kv"] = float(match_kv.group(1))
    
    # V -> kV (Seulement si > 100V pour éviter de capter "5V")
    if not match_kv:
        match_v = re.search(r'(\d+(?:\.\d+)?)\s*V(?!\w)', text, re.IGNORECASE) # (?!\w) pour ne pas matcher VA
        if match_v:
            val = float(match_v.group(1))
            if val > 100:
                extracted["voltage_kv"] = val / 1000.0

    # --- 3. DETECTION COURANT (A, kA) ---
    # kA -> A
    match_ka = re.search(r'(\d+(?:\.\d+)?)\s*kA', text, re.IGNORECASE)
    if match_ka:
        extracted["current_a"] = float(match_ka.group(1)) * 1000.0
        
    # A -> A
    if not match_ka:
        match_a = re.search(r'(\d+(?:\.\d+)?)\s*A(?!\w)', text, re.IGNORECASE) # (?!\w) évite "Ah"
        if match_a:
            extracted["current_a"] = float(match_a.group(1))

    # --- 4. DETECTION NOM (Optionnel, très basique) ---
    # Cherche TR-XXX ou TX-XXX
    match_name = re.search(r'(TX-[\w\d]+|TR-[\w\d]+|T[\d]+)', text, re.IGNORECASE)
    if match_name:
        extracted["detected_name"] = match_name.group(1).upper()
        
    return extracted

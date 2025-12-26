import re

def parse_technical_text(text: str) -> dict:
    """
    Parses a technical text to extract:
    - Power (normalized to kVA)
    - Voltage (normalized to kV)
    - Current (normalized to A)
    """
    
    # Basic cleanup
    text = text.replace(',', '.') # Handle French commas
    
    extracted = {
        "raw_text": text,
        "power_kva": None,
        "voltage_kv": None,
        "current_a": None,
        "detected_type": "UNKNOWN"
    }

    # --- 1. POWER DETECTION (MVA, kVA, MW) ---
    # Regex: Finds a number followed by MVA, kVA or MW
    # Ex: "63 MVA", "1000kVA", "2.5 MW"
    
    # MVA -> kVA
    match_mva = re.search(r'(\d+(?:\.\d+)?)\s*(?:MVA|MW)', text, re.IGNORECASE)
    if match_mva:
        val = float(match_mva.group(1))
        extracted["power_kva"] = val * 1000.0 # Convert to kVA
        extracted["detected_type"] = "TRANSFORMER" # Probably a transformer

    # kVA -> kVA
    if not match_mva:
        match_kva = re.search(r'(\d+(?:\.\d+)?)\s*kVA', text, re.IGNORECASE)
        if match_kva:
            extracted["power_kva"] = float(match_kva.group(1))
            extracted["detected_type"] = "TRANSFORMER"

    # --- 2. VOLTAGE DETECTION (kV, V) ---
    # kV -> kV
    match_kv = re.search(r'(\d+(?:\.\d+)?)\s*kV', text, re.IGNORECASE)
    if match_kv:
        extracted["voltage_kv"] = float(match_kv.group(1))
    
    # V -> kV (Only if > 100V to avoid matching "5V")
    if not match_kv:
        match_v = re.search(r'(\d+(?:\.\d+)?)\s*V(?!\w)', text, re.IGNORECASE) # (?!\w) to avoid matching VA
        if match_v:
            val = float(match_v.group(1))
            if val > 100:
                extracted["voltage_kv"] = val / 1000.0

    # --- 3. CURRENT DETECTION (A, kA) ---
    # kA -> A
    match_ka = re.search(r'(\d+(?:\.\d+)?)\s*kA', text, re.IGNORECASE)
    if match_ka:
        extracted["current_a"] = float(match_ka.group(1)) * 1000.0
        
    # A -> A
    if not match_ka:
        match_a = re.search(r'(\d+(?:\.\d+)?)\s*A(?!\w)', text, re.IGNORECASE) # (?!\w) avoids "Ah"
        if match_a:
            extracted["current_a"] = float(match_a.group(1))

    # --- 4. NAME DETECTION (Optional, very basic) ---
    # Looks for TR-XXX or TX-XXX
    match_name = re.search(r'(TX-[\w\d]+|TR-[\w\d]+|T[\d]+)', text, re.IGNORECASE)
    if match_name:
        extracted["detected_name"] = match_name.group(1).upper()
        
    return extracted

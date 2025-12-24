
FAULT_CATALOG = {
    "3PH": {"name": "Triphasé", "desc": "Défaut symétrique (L1-L2-L3). Base du calcul de stabilité.", "col_max": "IPPk3ph"},
    "2PH": {"name": "Biphasé", "desc": "Défaut phase-phase. Critique pour la sensibilité en bout de ligne.", "col_min": "IbLL"},
    "1PH": {"name": "Monophasé", "desc": "Défaut phase-terre. Utilisé pour les seuils Homopolaires (50N).", "col_max": "Icc1ph"}
}

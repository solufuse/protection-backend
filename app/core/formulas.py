
FORMULAS = {
    "ANSI_51_STAB": {
        "text": "I_setting > Icc_max_aval * k_stab",
        "vars": ["Icc_max_aval", "k_stab"]
    },
    "ANSI_51_SENS": {
        "text": "I_setting < Icc_min_end * k_sens",
        "vars": ["Icc_min_end", "k_sens"]
    },
    "INRUSH_CHECK": {
        "text": "I_setting > I_encl * 1.15",
        "vars": ["I_encl"]
    }
}

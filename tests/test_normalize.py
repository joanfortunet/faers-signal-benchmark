from faers.normalize import normalize_drug_name, strip_salt


def test_salt_is_removed():
    assert strip_salt("SERTRALINE HYDROCHLORIDE") == "SERTRALINE"
    assert strip_salt("ATORVASTATIN CALCIUM") == "ATORVASTATIN"


def test_hydrate_and_salt_are_removed():
    assert strip_salt("PAROXETINE HYDROCHLORIDE HEMIHYDRATE") == "PAROXETINE"


def test_inorganic_compounds_are_kept():
    assert strip_salt("LITHIUM CARBONATE") == "LITHIUM CARBONATE"
    assert strip_salt("MAGNESIUM SULFATE") == "MAGNESIUM SULFATE"
    assert strip_salt("POTASSIUM CHLORIDE") == "POTASSIUM CHLORIDE"


def test_single_word_is_never_emptied():
    assert strip_salt("SODIUM") == "SODIUM"


def test_esters_are_kept():
    assert strip_salt("FLUTICASONE PROPIONATE") == "FLUTICASONE PROPIONATE"


def test_combination_components_are_sorted_and_cleaned():
    assert normalize_drug_name("HYDROCODONE BITARTRATE\\ACETAMINOPHEN") == (
        "ACETAMINOPHEN\\HYDROCODONE"
    )
    assert normalize_drug_name("B\\A\\A") == "A\\B"

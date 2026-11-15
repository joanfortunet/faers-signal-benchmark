from faers.reference import classify_pairs, clean_text, mentions, to_us_spelling

LABEL = {
    "indications_and_usage": ["Indicated for the treatment of Asthma."],
    "warnings_and_cautions": ["5.1 Neuropsychiatric events: suicidal ideation and behavior."],
    "adverse_reactions": ["Peripheral edema, hemorrhage and diarrhea were reported."],
}


def test_british_terms_match_american_labels():
    assert to_us_spelling("Oedema peripheral") == "edema peripheral"
    assert to_us_spelling("Gastrointestinal haemorrhage") == "gastrointestinal hemorrhage"
    assert to_us_spelling("Diarrhoea") == "diarrhea"
    assert to_us_spelling("Anaemia") == "anemia"


def test_matching_uses_whole_words():
    text = clean_text("Hypertension and hyperkalemia.")
    assert mentions(text, "hypertension")
    assert not mentions(text, "tension")  # part of a word does not count


def test_pairs_are_classified_by_label_section():
    pts = ["suicidal ideation", "diarrhoea", "asthma", "alopecia"]
    status = {pt: s for _, pt, s in classify_pairs("MONTELUKAST", pts, LABEL)}
    assert status == {
        "suicidal ideation": "positive",  # warnings section
        "diarrhoea": "positive",  # adverse reactions, British spelling
        "asthma": "excluded",  # only the indication
        "alopecia": "negative",  # not on the label
    }

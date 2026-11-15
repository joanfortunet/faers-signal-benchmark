"""Normalise drug names so that the same molecule is always counted together.

FAERS stores the active ingredient as free text (prod_ai). The same molecule
appears with and without its salt (ATORVASTATIN vs ATORVASTATIN CALCIUM), and
combination products list their components in any order (A\\B vs B\\A).

Rules (applied to every component of a combination):
1. Drop a trailing hydrate word: MONOHYDRATE, ANHYDROUS...
2. Drop a trailing salt word: HYDROCHLORIDE, SODIUM, MESYLATE...
   unless what is left is itself an inorganic ion (MAGNESIUM SULFATE,
   LITHIUM CARBONATE and POTASSIUM CHLORIDE must stay as they are).
3. Sort the components of a combination alphabetically, without repeats.

Esters that change the pharmacology (PROPIONATE, FUROATE, VALERATE...)
are deliberately NOT removed, and fumarate esters such as DIMETHYL FUMARATE
are kept whole (see KEEP_WHOLE).
"""

HYDRATES = {
    "ANHYDROUS", "HYDRATE", "MONOHYDRATE", "DIHYDRATE", "TRIHYDRATE",
    "HEMIHYDRATE", "SESQUIHYDRATE",
}

SALTS = {
    "HYDROCHLORIDE", "DIHYDROCHLORIDE", "HCL", "HYDROBROMIDE", "SODIUM", "DISODIUM",
    "POTASSIUM", "CALCIUM", "MAGNESIUM", "ACETATE", "SULFATE", "MESYLATE", "DIMESYLATE",
    "MALEATE", "FUMARATE", "TARTRATE", "BITARTRATE", "SUCCINATE", "TOSYLATE",
    "BESYLATE", "CITRATE", "PHOSPHATE", "LACTATE", "GLUCONATE", "PAMOATE",
    "MEGLUMINE", "TROMETHAMINE", "BROMIDE", "CHLORIDE", "NITRATE", "CARBONATE",
    "HYCLATE", "MALATE", "OXALATE", "NAPSYLATE", "LYSINE", "ERBUMINE",
}

# Molecules whose last word looks like a salt but is part of the active
# moiety (esters): stripping it would leave a meaningless name (DIMETHYL).
KEEP_WHOLE = {
    "DIMETHYL FUMARATE", "DIROXIMEL FUMARATE", "MONOMETHYL FUMARATE",
}

INORGANIC_BASES = {
    "ALUMINIUM", "ALUMINUM", "AMMONIUM", "BARIUM", "CALCIUM", "CHROMIC", "COPPER",
    "CUPRIC", "FERRIC", "FERROUS", "IRON", "LITHIUM", "MAGNESIUM", "MANGANESE",
    "POTASSIUM", "SELENIUM", "SILVER", "SODIUM", "STRONTIUM", "ZINC",
}


def strip_salt(component):
    """'SERTRALINE HYDROCHLORIDE' -> 'SERTRALINE'; 'LITHIUM CARBONATE' stays."""
    if component in KEEP_WHOLE:
        return component
    words = component.split()
    if len(words) > 1 and words[-1] in HYDRATES:
        words = words[:-1]
    if len(words) > 1 and words[-1] in SALTS and " ".join(words[:-1]) not in INORGANIC_BASES:
        words = words[:-1]
    return " ".join(words)


def normalize_drug_name(name):
    """Normalise one (possibly combination) drug name. See the module docstring."""
    components = {strip_salt(part.strip()) for part in name.split("\\") if part.strip()}
    return "\\".join(sorted(components))


def build_drug_name_map(con):
    """Create drug_name_map(drug_name, drug) for every name in drug_clean."""
    names = [row[0] for row in con.execute("SELECT DISTINCT drug_name FROM drug_clean").fetchall()]
    normalised = [normalize_drug_name(name) for name in names]
    con.execute(
        "CREATE OR REPLACE TABLE drug_name_map AS "
        "SELECT UNNEST(?::VARCHAR[]) AS drug_name, UNNEST(?::VARCHAR[]) AS drug",
        [names, normalised],
    )

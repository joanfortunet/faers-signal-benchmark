-- Step 2: clean and deduplicate the raw tables.
--
-- Input:  raw_demo, raw_drug, raw_reac, raw_outc, raw_deleted (from faers.load)
-- Output: demo_dedup, drug_clean, reac_clean, outc_clean
--
-- drug_clean.drug_name is only cleaned text; salts and combinations are
-- normalised afterwards in Python (faers.normalize -> drug_name_map).
--
-- Why deduplicate? FAERS files are not cumulative: every time a case is
-- updated (new information, follow-up), a new version is published in a
-- later quarter with the same caseid and a new primaryid. Counting every
-- version would count the same patient several times.
--
-- Rule recommended by the FDA: for each caseid keep only the version with
-- the most recent fda_dt; if two versions share fda_dt, keep the one with
-- the highest primaryid. Cases listed as deleted are removed completely.


-- 1. Reports: one row per case (its latest version), with proper types.
CREATE OR REPLACE TABLE demo_dedup AS
WITH typed AS (
    SELECT
        quarter,
        TRY_CAST(primaryid AS BIGINT)                AS primaryid,
        TRY_CAST(caseid AS BIGINT)                   AS caseid,
        TRY_CAST(caseversion AS INTEGER)             AS caseversion,
        TRY_STRPTIME(fda_dt, '%Y%m%d')::DATE         AS fda_dt,
        TRY_STRPTIME(init_fda_dt, '%Y%m%d')::DATE    AS init_fda_dt,
        rept_cod,
        TRY_CAST(age AS DOUBLE)                      AS age,
        age_cod,
        NULLIF(sex, '')                              AS sex,
        NULLIF(occp_cod, '')                         AS occp_cod,
        NULLIF(reporter_country, '')                 AS reporter_country
    FROM raw_demo
),
deleted AS (
    SELECT DISTINCT TRY_CAST(caseid AS BIGINT) AS caseid FROM raw_deleted
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY caseid
            ORDER BY fda_dt DESC NULLS LAST, primaryid DESC
        ) AS version_rank
    FROM typed
    WHERE primaryid IS NOT NULL AND caseid IS NOT NULL
)
SELECT * EXCLUDE (version_rank)
FROM ranked
WHERE version_rank = 1
  AND caseid NOT IN (SELECT caseid FROM deleted WHERE caseid IS NOT NULL);


-- 2. Drugs of the kept reports.
--    The join uses primaryid AND quarter: a few primaryids appear in two
--    quarters, and we only want the rows published with the kept version.
--    drug_name is the active ingredient (prod_ai), falling back to the brand name
--    (drugname) when prod_ai is empty, in upper case with clean spaces.
--    Biosimilars carry a 4-letter FDA suffix (ADALIMUMAB-ADAZ, -ATTO...):
--    it is removed so that all of them count as the same molecule.
CREATE OR REPLACE TABLE drug_clean AS
SELECT DISTINCT
    d.primaryid,
    TRY_CAST(r.drug_seq AS INTEGER) AS drug_seq,
    r.role_cod,
    REGEXP_REPLACE(
        UPPER(TRIM(REGEXP_REPLACE(
            COALESCE(NULLIF(TRIM(r.prod_ai), ''), r.drugname), '\s+', ' ', 'g'
        ), ' .')),
        '-[A-Z]{4}$', ''
    )                               AS drug_name,
    r.drugname,
    r.prod_ai
FROM demo_dedup AS d
JOIN raw_drug AS r
  ON TRY_CAST(r.primaryid AS BIGINT) = d.primaryid
 AND r.quarter = d.quarter
WHERE COALESCE(NULLIF(TRIM(r.prod_ai), ''), NULLIF(TRIM(r.drugname), '')) IS NOT NULL;


-- 3. Reactions (MedDRA preferred terms) of the kept reports.
--    pt is stored in lower case so that 'Dyspnoea' and 'DYSPNOEA' match.
CREATE OR REPLACE TABLE reac_clean AS
SELECT DISTINCT
    d.primaryid,
    LOWER(TRIM(r.pt)) AS pt
FROM demo_dedup AS d
JOIN raw_reac AS r
  ON TRY_CAST(r.primaryid AS BIGINT) = d.primaryid
 AND r.quarter = d.quarter
WHERE NULLIF(TRIM(r.pt), '') IS NOT NULL;


-- 4. Outcomes (death, hospitalisation...) of the kept reports.
CREATE OR REPLACE TABLE outc_clean AS
SELECT DISTINCT
    d.primaryid,
    TRIM(o.outc_cod) AS outc_cod
FROM demo_dedup AS d
JOIN raw_outc AS o
  ON TRY_CAST(o.primaryid AS BIGINT) = d.primaryid
 AND o.quarter = d.quarter
WHERE NULLIF(TRIM(o.outc_cod), '') IS NOT NULL;

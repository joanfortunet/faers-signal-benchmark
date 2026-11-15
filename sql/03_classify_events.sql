-- Step 3: separate clinical reactions from non-clinical ones.
--
-- Input:  reac_clean, ref_non_clinical_pt (ref/non_clinical_pt_patterns.csv)
-- Output: pt_class (pt, category)
--
-- Many FAERS preferred terms are not adverse reactions: lack of efficacy
-- ('drug ineffective'), off-label use, medication errors, product or device
-- complaints, exposures during pregnancy... They are very frequent and give
-- huge, meaningless disproportionality scores, so they are kept out of the
-- benchmark. MedDRA's own hierarchy needs a licence, so the classification
-- uses the hand-written patterns in ref/non_clinical_pt_patterns.csv.
--
-- A pt matching several patterns gets the first category in alphabetical
-- order; anything that matches no pattern is 'clinical'.

CREATE OR REPLACE TABLE pt_class AS
SELECT
    p.pt,
    COALESCE(MIN(r.category), 'clinical') AS category
FROM (SELECT DISTINCT pt FROM reac_clean) AS p
LEFT JOIN ref_non_clinical_pt AS r
  ON REGEXP_MATCHES(p.pt, r.pattern)
GROUP BY p.pt;

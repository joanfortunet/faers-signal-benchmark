-- Step 3: drug-event contingency table, the input of every disproportionality method.
--
-- Input:  demo_dedup, drug_clean, reac_clean (from 02_clean_deduplicate.sql)
-- Output: report_drug_event, drug_event_counts
--
-- For every drug-event pair we need the classic 2x2 table:
--
--                      event        other events
--     drug               a               b          | n_drug
--     other drugs        c               d          |
--                     n_event                       | n_total
--
-- Only the primary suspect drug (role_cod = 'PS') is used, the same choice
-- as in the exploratory query. The universe (n_total) is every deduplicated
-- report with at least one primary suspect drug and one reaction.


-- 1. One row per (report, drug, event). A report with 2 drugs and 3 events
--    gives 6 rows. init_fda_dt (first time the FDA received the case) is kept
--    for the time-to-detection analysis later on.
CREATE OR REPLACE TABLE report_drug_event AS
SELECT DISTINCT
    dm.primaryid,
    dm.init_fda_dt,
    dr.drug,
    re.pt
FROM demo_dedup AS dm
JOIN drug_clean AS dr ON dr.primaryid = dm.primaryid AND dr.role_cod = 'PS'
JOIN reac_clean AS re ON re.primaryid = dm.primaryid;


-- 2. The 2x2 table for every observed pair.
CREATE OR REPLACE TABLE drug_event_counts AS
WITH total AS (
    SELECT COUNT(DISTINCT primaryid) AS n_total FROM report_drug_event
),
per_drug AS (
    SELECT drug, COUNT(DISTINCT primaryid) AS n_drug
    FROM report_drug_event
    GROUP BY drug
),
per_event AS (
    SELECT pt, COUNT(DISTINCT primaryid) AS n_event
    FROM report_drug_event
    GROUP BY pt
),
pairs AS (
    SELECT drug, pt, COUNT(DISTINCT primaryid) AS a
    FROM report_drug_event
    GROUP BY drug, pt
)
SELECT
    p.drug,
    p.pt,
    p.a,
    d.n_drug - p.a                              AS b,
    e.n_event - p.a                             AS c,
    t.n_total - d.n_drug - e.n_event + p.a      AS d,
    d.n_drug,
    e.n_event,
    t.n_total
FROM pairs AS p
JOIN per_drug AS d ON d.drug = p.drug
JOIN per_event AS e ON e.pt = p.pt
CROSS JOIN total AS t;

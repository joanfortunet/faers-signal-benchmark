-- Exploratory query: PRR for every reaction of one drug (one quarter).
--
-- Tables used: demo_2026q2 (all reports), drug_2026q2 (drugs), reac_2026q2 (reactions).
-- Only reports where the drug is the primary suspect (role_cod = 'PS') are counted.
--
-- To experiment:
--   * change prod_ai in drug_reports to analyse another drug
--   * change the minimum count (b.a >= N) in the last WHERE

WITH n AS (
    SELECT COUNT(*) AS total FROM demo_2026q2
),
drug_reports AS (
    SELECT DISTINCT primaryid
    FROM drug_2026q2
    WHERE role_cod = 'PS' AND prod_ai = 'SEMAGLUTIDE'
),
drug_n AS (
    SELECT COUNT(*) AS drug_total FROM drug_reports
),
event_counts AS (
    SELECT pt, COUNT(DISTINCT primaryid) AS event_total
    FROM reac_2026q2
    GROUP BY pt
),
both_counts AS (
    SELECT r.pt, COUNT(DISTINCT r.primaryid) AS a
    FROM reac_2026q2 AS r
    JOIN drug_reports AS d ON r.primaryid = d.primaryid
    GROUP BY r.pt
)
SELECT
    b.pt,
    b.a,
    e.event_total,
    ROUND(
        (b.a * 1.0 / dn.drug_total)
        / ((e.event_total - b.a) * 1.0 / (n.total - dn.drug_total)),
    2) AS prr
FROM both_counts AS b
JOIN event_counts AS e ON b.pt = e.pt
CROSS JOIN n
CROSS JOIN drug_n AS dn
WHERE b.a >= 3
ORDER BY prr DESC
LIMIT 15;
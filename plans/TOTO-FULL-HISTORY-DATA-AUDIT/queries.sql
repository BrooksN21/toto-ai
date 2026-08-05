-- Read-only key checks for TOTO-FULL-HISTORY-DATA-AUDIT.
-- Run with:
-- sqlite3 -readonly -header -column data/toto.db \
--   < plans/TOTO-FULL-HISTORY-DATA-AUDIT/queries.sql

PRAGMA quick_check;

SELECT name, COUNT(*) AS drawings, MIN(number) AS min_number,
       MAX(number) AS max_number, MIN(id) AS min_id, MAX(id) AS max_id
FROM drawings
GROUP BY name
ORDER BY drawings DESC;

SELECT 'drawings' AS table_name, COUNT(*) AS rows FROM drawings
UNION ALL SELECT 'events', COUNT(*) FROM events
UNION ALL SELECT 'quotes', COUNT(*) FROM quotes
UNION ALL SELECT 'drawing_result_snapshots', COUNT(*) FROM drawing_result_snapshots
UNION ALL SELECT 'drawing_preparations', COUNT(*) FROM drawing_preparations
UNION ALL SELECT 'drawing_event_pins', COUNT(*) FROM drawing_event_pins
UNION ALL SELECT 'archived_packages', COUNT(*) FROM archived_packages
UNION ALL SELECT 'package_settlements', COUNT(*) FROM package_settlements;

WITH RECURSIVE numbers(value) AS (
  SELECT MIN(number) FROM drawings WHERE name = 'baltbet-main'
  UNION ALL
  SELECT value + 1 FROM numbers
  WHERE value < (SELECT MAX(number) FROM drawings WHERE name = 'baltbet-main')
)
SELECT value AS missing_visible_number
FROM numbers
LEFT JOIN drawings
  ON drawings.name = 'baltbet-main' AND drawings.number = numbers.value
WHERE drawings.id IS NULL;

SELECT number, COUNT(*) AS rows, GROUP_CONCAT(id) AS internal_ids
FROM drawings
WHERE name = 'baltbet-main'
GROUP BY number
HAVING COUNT(*) > 1
ORDER BY number;

WITH event_coverage AS (
  SELECT drawing_id,
         COUNT(*) AS event_count,
         COUNT(DISTINCT event_order) AS unique_orders,
         SUM(CASE WHEN name IS NULL OR TRIM(name) = '' THEN 1 ELSE 0 END)
           AS blank_names,
         SUM(CASE WHEN result IN ('1', 'X', '2') THEN 1 ELSE 0 END)
           AS resolved_results,
         SUM(CASE WHEN result = '*' THEN 1 ELSE 0 END) AS void_results,
         SUM(CASE WHEN result IS NULL OR TRIM(result) = '' THEN 1 ELSE 0 END)
           AS missing_results
  FROM events
  GROUP BY drawing_id
),
quote_coverage AS (
  SELECT drawing_id,
         COUNT(*) AS quote_rows,
         COUNT(DISTINCT event_order) AS unique_orders,
         SUM(CASE WHEN pool_win_1 IS NOT NULL AND pool_draw IS NOT NULL
                       AND pool_win_2 IS NOT NULL THEN 1 ELSE 0 END)
           AS pool_complete,
         SUM(CASE WHEN bk_win_1 IS NOT NULL AND bk_draw IS NOT NULL
                       AND bk_win_2 IS NOT NULL THEN 1 ELSE 0 END)
           AS bk_complete,
         SUM(CASE WHEN norm_win_1 IS NOT NULL AND norm_draw IS NOT NULL
                       AND norm_win_2 IS NOT NULL THEN 1 ELSE 0 END)
           AS norm_complete,
         SUM(CASE WHEN pin_win_1 IS NOT NULL AND pin_draw IS NOT NULL
                       AND pin_win_2 IS NOT NULL THEN 1 ELSE 0 END)
           AS pin_complete
  FROM quotes
  GROUP BY drawing_id
)
SELECT d.number, d.id, d.status, d.started_at, d.ended_at,
       e.event_count, e.unique_orders AS unique_event_orders, e.blank_names,
       COALESCE(q.quote_rows, 0) AS quote_rows,
       COALESCE(q.pool_complete, 0) AS pool_complete,
       COALESCE(q.bk_complete, 0) AS bk_complete,
       COALESCE(q.norm_complete, 0) AS norm_complete,
       COALESCE(q.pin_complete, 0) AS pin_complete,
       e.resolved_results, e.void_results, e.missing_results
FROM drawings AS d
JOIN event_coverage AS e ON e.drawing_id = d.id
LEFT JOIN quote_coverage AS q ON q.drawing_id = d.id
WHERE d.name = 'baltbet-main'
ORDER BY d.number;

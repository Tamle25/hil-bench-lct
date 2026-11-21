SELECT region, COUNT(*) AS late_orders
FROM orders
WHERE status = 'DELIVERED'
  AND delivered_at >= '2026-09-07 00:00:00'
  AND delivered_at < '2026-09-14 00:00:00'
  AND delivered_at > COALESCE(adjusted_due_at, original_due_at)
GROUP BY region;

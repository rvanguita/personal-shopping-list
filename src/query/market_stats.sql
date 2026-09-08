SELECT 
    market_id
    , ROUND(SUM(product_price), 2) AS total_spent
    , ROUND(SUM(product_price) / COUNT(DISTINCT purchase_date), 2) AS avg_ticket
    , COUNT(DISTINCT purchase_date) AS visit_count
    , MAX(purchase_date) AS last_visit
FROM bronze_purchases
GROUP BY market_id
ORDER BY total_spent DESC


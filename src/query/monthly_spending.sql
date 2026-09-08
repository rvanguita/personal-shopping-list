SELECT
    DATE_FORMAT(purchase_date, '%Y-%m') AS `year_month`
    , ROUND(SUM(product_price), 2) AS total_spent
    , COUNT(*) AS item_count
    , ROUND(AVG(product_price), 2) AS avg_price
FROM bronze_purchases
GROUP BY DATE_FORMAT(purchase_date, '%Y-%m')
ORDER BY `year_month`


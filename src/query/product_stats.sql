SELECT 
    product_id
    , MAX(purchase_date) AS last_purchase_date
    , ROUND(AVG(days_between), 2) AS avg_days_purchase
    , ROUND(AVG(product_price), 2) AS avg_product_price
    , ROUND(MIN(product_price), 2) AS min_product_price
    , ROUND(MAX(product_price), 2) AS max_product_price
    , COUNT(*) AS total_purchases
    , ROUND(DATEDIFF(CURDATE(), MAX(purchase_date)), 2) AS days_last_purchase
FROM (
    SELECT 
        product_id
        , purchase_date
        , product_price
        , DATEDIFF(
            purchase_date, 
            LAG(purchase_date) OVER (PARTITION BY product_id ORDER BY purchase_date)
          ) AS days_between
    FROM bronze_purchases
) sub
GROUP BY product_id
ORDER BY last_purchase_date DESC


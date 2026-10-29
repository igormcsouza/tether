*   `top_n` in shop/rank.py: sorts in ascending order by default, but docstring says "best first" (descending order expected) - should use `reverse=True`
*   `share` in shop/rank.py: no handling for division by zero when total sales is 0

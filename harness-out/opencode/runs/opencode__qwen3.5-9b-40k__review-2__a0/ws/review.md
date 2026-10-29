# Code Review Findings: shop/stock.py

- **restock**: Docstring says "Add qty units to the stock" (implies increment: `stock += qty`), but implementation replaces (`stock = qty`).
- **low_stock**: Docstring says "strictly below threshold" (`stock < threshold`), but implementation uses `stock <= threshold`.
- **total_units**: Missing docstring.

"""Stock keeping."""


class Inventory:
    def __init__(self):
        self._items = {}

    def add(self, sku, name, price, stock=0):
        if sku in self._items:
            raise KeyError(f"duplicate sku {sku}")
        self._items[sku] = {"sku": sku, "name": name, "price": price, "stock": stock}

    def get(self, sku):
        return self._items[sku]

    def remove_stock(self, sku, qty):
        item = self._items[sku]
        if qty > item["stock"]:
            raise ValueError("insufficient stock")
        item["stock"] -= qty

    def list_items(self, page=1, page_size=None):
        """List items with optional pagination.
        
        Args:
            page: Page number (1-indexed). Default is 1.
            page_size: Number of items per page. If None, returns all items.
        
        Returns:
            List of item dictionaries for the requested page, or all items if page_size is None.
        """
        all_items = sorted(self._items.values(), key=lambda i: i["sku"])
        
        if page_size is None:
            return all_items
        
        # Calculate start and end indices (1-indexed page)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        return all_items[start_idx:end_idx]
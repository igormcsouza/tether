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

    def list_items(self, page=1, page_size=100):
        """List all items, optionally paginated.
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            
        Returns:
            A slice of items from the current page
        """
        items = sorted(self._items.values(), key=lambda i: i["sku"])
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end]
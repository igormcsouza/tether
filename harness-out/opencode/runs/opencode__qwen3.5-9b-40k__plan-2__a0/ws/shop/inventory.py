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

    def list_items(self):
        return sorted(self._items.values(), key=lambda i: i["sku"])

    def low_stock_alerts(self, threshold: int | None = None) -> list[dict]:
        if threshold is None:
            threshold = 5
        return [
            {
                "sku": i["sku"],
                "name": i["name"],
                "price": i["price"],
                "stock": i["stock"],
                "shortage": threshold - i["stock"],
            }
            for i in self._items.values()
            if i["stock"] < threshold
        ]

"""Price cache."""
_cache = {}


def cached_price(sku, load):
    if sku not in _cache:
        _cache[sku] = load(sku)
    return _cache[sku]


def clear():
    _cache.clear()

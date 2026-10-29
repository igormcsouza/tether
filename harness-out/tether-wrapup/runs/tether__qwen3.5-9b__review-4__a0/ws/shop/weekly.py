"""Weekly job."""
from shop.rank import top_n, share


def weekly(sales):
    best = top_n(sales, 3)
    return [(s, round(share(sales, s) * 100)) for s in best]

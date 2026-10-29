"""Tax calculations."""


def rate(region):
    """Return the tax rate for a given region as a decimal."""
    if region == "US-CA":
        return 0.0725
    elif region == "US-NY":
        return 0.04
    elif region == "EU":
        return 0.20
    else:
        return 0.0

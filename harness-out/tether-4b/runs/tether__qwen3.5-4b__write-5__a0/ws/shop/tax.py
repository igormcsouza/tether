"""Sales tax rates by region."""


def rate(region):
    """Return the sales tax rate for a given region as a decimal.
    
    US-CA: 7.25%
    US-NY: 4%
    EU: 20%
    Other regions: 0%
    """
    rates = {
        "US-CA": 0.0725,
        "US-NY": 0.04,
        "EU": 0.20,
    }
    return rates.get(region, 0.0)
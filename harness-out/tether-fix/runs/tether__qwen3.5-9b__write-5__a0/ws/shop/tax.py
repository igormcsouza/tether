"""Tax rates by region."""


def rate(region):
    """Return the sales tax rate for a given region.
    
    Args:
        region: The region code (e.g., "US-CA", "US-NY", "EU", or any other string)
    
    Returns:
        The tax rate as a decimal (e.g., 0.0725 for 7.25%)
    """
    rates = {
        "US-CA": 0.0725,
        "US-NY": 0.04,
        "EU": 0.20,
    }
    return rates.get(region, 0.0)
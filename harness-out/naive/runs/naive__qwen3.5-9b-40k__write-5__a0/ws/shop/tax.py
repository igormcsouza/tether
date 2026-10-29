"""Sales tax rates by region."""


def rate(region):
    """Return the sales tax rate for a given region.
    
    Args:
        region: The region code (e.g., "US-CA", "US-NY", "EU", etc.)
    
    Returns:
        The tax rate as a decimal (e.g., 0.0725 for 7.25%)
    """
    if region == "US-CA":
        return 0.0725
    elif region == "US-NY":
        return 0.04
    elif region == "EU":
        return 0.20
    else:
        return 0.0

def calculate_total(amount):
    """Reject negative amounts and apply a discount at the inclusive threshold."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if amount >= 1000:
        return amount * 0.9
    return amount

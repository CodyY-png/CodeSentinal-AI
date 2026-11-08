def calculate_total(amount):
    """Demo with intentional bugs: incorrect threshold and missing validation."""
    if amount > 1000:
        return amount * 0.9
    return amount

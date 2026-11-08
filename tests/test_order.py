import pytest

from demo_app.order import calculate_total


def test_regular_amount():
    assert calculate_total(500) == 500


def test_discount_above_threshold():
    assert calculate_total(1500) == pytest.approx(1350)


def test_discount_at_threshold():
    assert calculate_total(1000) == pytest.approx(900)


def test_negative_amount_is_rejected():
    with pytest.raises(ValueError):
        calculate_total(-100)

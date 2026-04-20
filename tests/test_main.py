import pytest

from src.calculator import add, divide, multiply, subtract


def test_add() -> None:
    assert add(2, 3) == 5


def test_subtract() -> None:
    assert subtract(10, 4) == 6


def test_multiply() -> None:
    assert multiply(3, 4) == 12


def test_divide() -> None:
    assert divide(6, 2) == 3
    assert divide(5, 2) == 2.5


def test_divide_by_zero() -> None:
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(1, 0)

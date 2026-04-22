import pytest

from src.calculator import (
    abs_value,
    add,
    divide,
    modulo,
    multiply,
    power,
    sqrt_value,
    subtract,
)


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


def test_power() -> None:
    assert power(2, 8) == 256


def test_modulo() -> None:
    assert modulo(10, 3) == 1


def test_modulo_by_zero() -> None:
    with pytest.raises(ValueError, match="Cannot take modulo by zero"):
        modulo(1, 0)


def test_sqrt_value() -> None:
    assert sqrt_value(4) == 2
    assert sqrt_value(9) == 3
    assert sqrt_value(0) == 0


def test_sqrt_value_negative() -> None:
    with pytest.raises(
        ValueError, match="Cannot take square root of a negative number"
    ):
        sqrt_value(-1)


def test_abs_value() -> None:
    assert abs_value(5) == 5
    assert abs_value(-3) == 3
    assert abs_value(0) == 0

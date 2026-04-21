import sys
from argparse import ArgumentParser
from collections.abc import Callable

from src.calculator import add, divide, modulo, multiply, power, subtract

OperationFunc = Callable[[float, float], float]

OPERATIONS: dict[str, tuple[str, OperationFunc]] = {
    "add": ("add", add),
    "sum": ("add", add),
    "subtract": ("subtract", subtract),
    "sub": ("subtract", subtract),
    "multiply": ("multiply", multiply),
    "mul": ("multiply", multiply),
    "divide": ("divide", divide),
    "div": ("divide", divide),
    "power": ("power", power),
    "pow": ("power", power),
    "modulo": ("modulo", modulo),
    "mod": ("modulo", modulo),
}

EXIT_COMMANDS = {"exit", "quit", "q"}
INTERACTIVE_COMMANDS = {"interactive", "i"}
HELP_COMMANDS = {"help", "h"}


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Simple calculator CLI")
    parser.add_argument(
        "operation",
        nargs="?",
        help="Operation: add, subtract, multiply, divide, power, modulo or interactive",
    )
    parser.add_argument("a", nargs="?", type=float, help="First number")
    parser.add_argument("b", nargs="?", type=float, help="Second number")
    return parser


def format_result(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def show_examples() -> None:
    print("Simple calculator CLI")
    print("Examples:")
    print("  python -m src.main add 2 3")
    print("  python -m src.main sub 10 4")
    print("  python -m src.main mul 6 7")
    print("  python -m src.main div 5 2")
    print("  python -m src.main pow 2 8")
    print("  python -m src.main mod 10 3")
    print("  python -m src.main interactive")


def get_operation(operation: str) -> tuple[str, OperationFunc]:
    normalized = operation.strip().lower()
    try:
        return OPERATIONS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown operation: {operation}") from exc


def calculate(operation: str, a: float, b: float) -> float:
    _, func = get_operation(operation)
    return func(a, b)


def run_interactive() -> None:
    print("Interactive calculator mode")
    print("Type help to see operations or exit to quit.")

    while True:
        operation = input("operation> ").strip().lower()

        if operation in EXIT_COMMANDS:
            print("Bye!")
            return

        if operation in HELP_COMMANDS:
            print("Available operations: add, sub, mul, div, pow, mod")
            continue

        try:
            _, func = get_operation(operation)
            a = float(input("a> ").strip())
            b = float(input("b> ").strip())
            result = func(a, b)
        except ValueError as exc:
            print(exc)
            continue

        print(f"= {format_result(result)}")


def main() -> None:
    if len(sys.argv) == 1:
        show_examples()
        return

    parser = build_parser()
    args = parser.parse_args()

    if args.operation is not None and args.operation.lower() in INTERACTIVE_COMMANDS:
        run_interactive()
        return

    if args.operation is None or args.a is None or args.b is None:
        parser.error("Operation and two numbers are required in normal mode")

    try:
        result = calculate(args.operation, args.a, args.b)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(format_result(result))


if __name__ == "__main__":
    main()

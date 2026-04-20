import sys
from argparse import ArgumentParser

from src.calculator import add, divide, multiply, subtract


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Simple calculator CLI")
    parser.add_argument(
        "operation",
        choices=["add", "subtract", "multiply", "divide"],
        help="Operation to perform",
    )
    parser.add_argument("a", type=float, help="First number")
    parser.add_argument("b", type=float, help="Second number")
    return parser


def format_result(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def main() -> None:
    if len(sys.argv) == 1:
        print("Simple calculator CLI")
        print("Examples:")
        print("  python -m src.main add 2 3")
        print("  python -m src.main subtract 10 4")
        print("  python -m src.main multiply 6 7")
        print("  python -m src.main divide 5 2")
        return

    parser = build_parser()
    args = parser.parse_args()

    operations = {
        "add": add,
        "subtract": subtract,
        "multiply": multiply,
        "divide": divide,
    }

    try:
        result = operations[args.operation](args.a, args.b)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(format_result(result))


if __name__ == "__main__":
    main()

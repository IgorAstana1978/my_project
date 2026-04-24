import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from typing import cast

from src.calculator import add, divide, modulo, multiply, power, subtract

OperationFunc = Callable[[float, float], float]
OperationSpec = tuple[str, list[str], str, OperationFunc]

OPERATION_SPECS: tuple[OperationSpec, ...] = (
    ("add", ["sum"], "Add two numbers", add),
    ("subtract", ["sub"], "Subtract two numbers", subtract),
    ("multiply", ["mul"], "Multiply two numbers", multiply),
    ("divide", ["div"], "Divide two numbers", divide),
    ("power", ["pow"], "Raise first number to the power of second", power),
    ("modulo", ["mod"], "Get remainder from division", modulo),
)

EXIT_COMMANDS = {"exit", "quit", "q"}
HELP_COMMANDS = {"help", "h"}
HISTORY_COMMANDS = {"history"}
CLEAR_COMMANDS = {"clear"}


def format_result(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def parse_number(text: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError("Please enter a valid number") from exc


def build_operation_maps() -> tuple[dict[str, str], dict[str, OperationFunc]]:
    aliases_to_name: dict[str, str] = {}
    funcs_by_name: dict[str, OperationFunc] = {}

    for name, aliases, _, func in OPERATION_SPECS:
        aliases_to_name[name] = name
        funcs_by_name[name] = func

        for alias in aliases:
            aliases_to_name[alias] = name

    return aliases_to_name, funcs_by_name


ALIASES_TO_NAME, FUNCS_BY_NAME = build_operation_maps()


def resolve_operation(operation: str) -> tuple[str, OperationFunc]:
    normalized = operation.strip().lower()

    try:
        canonical_name = ALIASES_TO_NAME[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown operation: {operation}") from exc

    return canonical_name, FUNCS_BY_NAME[canonical_name]


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m src.main",
        description="Simple calculator CLI with subcommands.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    for name, aliases, help_text, func in OPERATION_SPECS:
        subparser = subparsers.add_parser(
            name,
            aliases=aliases,
            help=help_text,
            description=help_text,
        )
        subparser.add_argument("a", type=float, help="First number")
        subparser.add_argument("b", type=float, help="Second number")
        subparser.set_defaults(mode="operation", func=func)

    interactive_parser = subparsers.add_parser(
        "interactive",
        aliases=["i"],
        help="Run interactive calculator mode",
        description="Run interactive calculator mode",
    )
    interactive_parser.set_defaults(mode="interactive")

    return parser


def run_interactive() -> None:
    history: list[str] = []

    print("Interactive calculator mode")
    print("Commands: add, sub, mul, div, pow, mod, history, clear, help, exit")

    while True:
        try:
            raw_command = input("calc> ").strip()
        except EOFError, KeyboardInterrupt:
            print("\nBye!")
            return

        if raw_command == "":
            continue

        command = raw_command.lower()

        if command in EXIT_COMMANDS:
            print("Bye!")
            return

        if command in HELP_COMMANDS:
            print("Commands: add, sub, mul, div, pow, mod, history, clear, help, exit")
            continue

        if command in HISTORY_COMMANDS:
            if history:
                print("History:")
                for item in history:
                    print(item)
            else:
                print("History is empty.")
            continue

        if command == "history export" or command.startswith("history export "):
            path = command[15:].strip() if command.startswith("history export ") else ""
            if not path:
                print("Usage: history export <filepath>")
                continue
            if not history:
                print("History is empty. Nothing to export.")
                continue
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for item in history:
                        f.write(item + "\n")
                print(f"History exported to {path}")
            except OSError as exc:
                print(f"Failed to export: {exc}")
            continue

        if command in CLEAR_COMMANDS:
            history.clear()
            print("History cleared.")
            continue

        try:
            canonical_name, func = resolve_operation(command)
            a = parse_number(input("a> ").strip())
            b = parse_number(input("b> ").strip())
            result = func(a, b)
        except ValueError as exc:
            print(exc)
            continue

        entry = (
            f"{canonical_name} "
            f"{format_result(a)} {format_result(b)} = {format_result(result)}"
        )
        history.append(entry)
        print(entry)


def main() -> None:
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()

    if getattr(args, "mode", None) == "interactive":
        run_interactive()
        return

    func = cast(OperationFunc, args.func)
    operation_args = cast(Namespace, args)
    result = func(operation_args.a, operation_args.b)
    print(format_result(result))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

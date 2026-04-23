import sys
from argparse import ArgumentParser
from collections.abc import Callable
from typing import cast

from .calculator import (
    abs_value,
    add,
    divide,
    modulo,
    multiply,
    power,
    sqrt_value,
    subtract,
)

type UnaryOperationFunc = Callable[[float], float]
type BinaryOperationFunc = Callable[[float, float], float]
type OperationFunc = UnaryOperationFunc | BinaryOperationFunc
type OperationSpec = tuple[str, list[str], str, int, OperationFunc]

OPERATION_SPECS: tuple[OperationSpec, ...] = (
    ("add", ["sum"], "Add two numbers", 2, add),
    ("subtract", ["sub"], "Subtract two numbers", 2, subtract),
    ("multiply", ["mul"], "Multiply two numbers", 2, multiply),
    ("divide", ["div"], "Divide two numbers", 2, divide),
    ("power", ["pow"], "Raise first number to the power of second", 2, power),
    ("modulo", ["mod"], "Get remainder from division", 2, modulo),
    ("sqrt", [], "Square root of a number", 1, sqrt_value),
    ("abs", [], "Absolute value of a number", 1, abs_value),
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


def build_operation_maps() -> (
    tuple[dict[str, str], dict[str, tuple[int, OperationFunc]]]
):
    aliases_to_name: dict[str, str] = {}
    funcs_by_name: dict[str, tuple[int, OperationFunc]] = {}

    for name, aliases, _, arity, func in OPERATION_SPECS:
        aliases_to_name[name] = name
        funcs_by_name[name] = (arity, func)

        for alias in aliases:
            aliases_to_name[alias] = name

    return aliases_to_name, funcs_by_name


ALIASES_TO_NAME, FUNCS_BY_NAME = build_operation_maps()


def resolve_operation(operation: str) -> tuple[str, int, OperationFunc]:
    for name, aliases, _, arity, func in OPERATION_SPECS:
        if operation == name or operation in aliases:
            return name, arity, func
    raise ValueError(f"Unknown operation: {operation}")


def build_interactive_help_message() -> str:
    display_names: list[str] = []

    for name, aliases, _, _, _ in OPERATION_SPECS:
        if name in {"subtract", "multiply", "divide", "power", "modulo"}:
            display_names.append(aliases[0])
        else:
            display_names.append(name)

    special_commands = [
        command
        for command in ("history", "clear", "help", "exit")
        if (
            command in HISTORY_COMMANDS
            or command in CLEAR_COMMANDS
            or command in HELP_COMMANDS
            or command in EXIT_COMMANDS
        )
    ]

    return f"Commands: {', '.join(display_names + special_commands)}"


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m src.main",
        description="Simple calculator CLI with subcommands.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    for name, aliases, help_text, arity, func in OPERATION_SPECS:
        subparser = subparsers.add_parser(
            name,
            aliases=aliases,
            help=help_text,
            description=help_text,
        )
        subparser.add_argument("a", type=float, help="First number")
        if arity == 2:
            subparser.add_argument("b", type=float, help="Second number")
        subparser.set_defaults(mode="operation", func=func, arity=arity)

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
    print(build_interactive_help_message())

    while True:
        try:
            command = input("calc> ").strip().lower()
        except EOFError, KeyboardInterrupt:
            print("Bye!")
            return

        if command in EXIT_COMMANDS:
            print("Bye!")
            return

        if command in HELP_COMMANDS:
            print(build_interactive_help_message())
            continue

        if command in HISTORY_COMMANDS:
            if history:
                print("History:")
                for item in history:
                    print(item)
            else:
                print("History is empty.")
            continue

        if command in CLEAR_COMMANDS:
            history.clear()
            print("History cleared.")
            continue

        try:
            canonical_name, arity, func = resolve_operation(command)

            if arity == 1:
                number = parse_number(input("number> ").strip())
                unary_func = cast(UnaryOperationFunc, func)
                result = unary_func(number)
                entry = (
                    f"{canonical_name} {format_result(number)} = "
                    f"{format_result(result)}"
                )
            else:
                a = parse_number(input("a> ").strip())
                b = parse_number(input("b> ").strip())
                binary_func = cast(BinaryOperationFunc, func)
                result = binary_func(a, b)
                entry = (
                    f"{canonical_name} {format_result(a)} {format_result(b)} = "
                    f"{format_result(result)}"
                )

        except ValueError as exc:
            print(exc)
            continue

        history.append(entry)
        print(entry)


def main() -> None:
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()

    if args.mode == "interactive":
        run_interactive()
        return

    func = cast(OperationFunc, args.func)
    arity = cast(int, args.arity)

    try:
        if arity == 1:
            unary_func = cast(UnaryOperationFunc, func)
            result = unary_func(args.a)
        else:
            binary_func = cast(BinaryOperationFunc, func)
            result = binary_func(args.a, args.b)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print(format_result(result))


if __name__ == "__main__":
    main()

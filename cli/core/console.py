from contextlib import contextmanager
from typing import Any, Generator, Sequence

from rich.console import Console
from rich.table import Table

console = Console()


def info(msg: str) -> None:
    console.print(f"[bold blue]ℹ[/] {msg}")


def success(msg: str) -> None:
    console.print(f"[bold green]✓[/] {msg}")


def warning(msg: str) -> None:
    console.print(f"[bold yellow]⚠[/] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]✗[/] {msg}")


@contextmanager
def status_spinner(msg: str) -> Generator[None, None, None]:
    with console.status(f"[bold cyan]{msg}..."):
        yield


def print_table(title: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(col, style="cyan")
    for row in rows:
        table.add_row(*(str(v) for v in row))
    console.print(table)

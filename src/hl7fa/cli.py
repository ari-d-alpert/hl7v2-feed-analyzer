"""Command-line interface for hl7fa."""
from __future__ import annotations

import sys

import click
import pandas as pd
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import (
    analyze_field,
    fillrate_frame,
    fillrate_by_message_type,
    values_frame,
    group,
    integrity_frame,
    summary,
    timeline,
    load,
)

console = Console()


def _parse_ext(ext: str) -> tuple[str, ...]:
    return tuple(e if e.startswith(".") else "." + e
                 for e in (x.strip() for x in ext.split(",")) if e)


def _emit(df: pd.DataFrame, fmt: str, out: str | None, title: str) -> None:
    """Render a DataFrame to the chosen format."""
    if fmt == "csv":
        if out:
            df.to_csv(out, index=False)
            console.print(f"[green]wrote[/] {out}")
        else:
            click.echo(df.to_csv(index=False))
    elif fmt == "json":
        if out:
            df.to_json(out, orient="records", indent=2)
            console.print(f"[green]wrote[/] {out}")
        else:
            click.echo(df.to_json(orient="records", indent=2))
    else:  # table
        table = Table(title=title, header_style="bold cyan")
        for col in df.columns:
            table.add_column(str(col))
        for _, row in df.iterrows():
            table.add_row(*[str(v) for v in row.tolist()])
        console.print(table)


_OTHER_KEY = {"account": "visit", "visit": "account"}


def _no_timeline_match(kind: str, value: str, *, encounter_key: str, messages,
                       mrn_spec: str, account_spec: str, visit_spec: str) -> None:
    """Report an empty timeline lookup and exit.

    For an encounter miss, re-group under the opposite key: an account number
    asked for while grouping by visit (or vice versa) is the common mistake,
    and saying so is more useful than "not found".
    """
    console.print(
        f"[red]No {kind} matching[/] {escape(repr(value))}"
        + (f" [red]under[/] --encounter-key={encounter_key}." if kind == "encounter" else ".")
    )
    if kind == "encounter":
        other = _OTHER_KEY[encounter_key]
        other_grp = group(messages, encounter_key=other, mrn_spec=mrn_spec,
                          account_spec=account_spec, visit_spec=visit_spec)
        if value in other_grp.encounters:
            console.print(
                f"That ID is an encounter under [bold]--encounter-key={other}[/]; "
                f"rerun with that flag."
            )
    sys.exit(1)


@click.group()
@click.version_option()
def main() -> None:
    """Population-level analysis for HL7 v2 feeds.

    Parsing HL7 is solved; understanding a whole feed is not. These commands
    report field fill rates and reconstruct encounters from an ADT stream.
    """


@main.command()
@click.argument("path")
@click.argument("fields", nargs=-1, required=True)
@click.option("--ext", default=".hl7,.txt,.dat", help="Comma-separated file extensions.")
@click.option("--top", default=20, help="Show top-N values per field (0 = all).")
@click.option("--values", "show_values", is_flag=True, help="Show value distribution per field.")
@click.option("--by-message-type", is_flag=True, help="Break fill rate down by MSH-9 trigger.")
@click.option("--format", "fmt", type=click.Choice(["table", "csv", "json"]), default="table")
@click.option("--out", default=None, help="Write output to file instead of stdout.")
def fillrate(path, fields, ext, top, show_values, by_message_type, fmt, out):
    """Field fill rates and value distributions.

    FIELDS use SEG-N[.C[.S]] notation, e.g. PID-3 PV1-2 PID-18 DG1-3.1
    """
    result = load(path, _parse_ext(ext))
    if not result.messages:
        console.print("[red]No messages parsed.[/] Check the path and --ext.")
        sys.exit(1)
    console.print(
        f"[dim]Loaded {len(result.messages)} messages from "
        f"{result.files_read} file(s); skipped {result.skipped}.[/]"
    )

    if by_message_type:
        frames = [fillrate_by_message_type(result.messages, f) for f in fields]
        _emit(pd.concat(frames, ignore_index=True), fmt, out,
              "Fill rate by message type")
        return

    reports = [analyze_field(result.messages, f, top=top) for f in fields]
    _emit(fillrate_frame(reports), fmt, out, "Fill rates")

    if show_values:
        for r in reports:
            df = values_frame(r, all_values=(top == 0))
            _emit(df, fmt, None, f"Values: {r.spec}")


@main.command()
@click.argument("path")
@click.option("--encounter-key", type=click.Choice(["account", "visit"]), default="account",
              help="Group encounters by account number (PID-18) or visit number (PV1-19).")
@click.option("--mrn-spec", default="PID-3.1", help="Field spec for MRN.")
@click.option("--account-spec", default="PID-18.1", help="Field spec for account number.")
@click.option("--visit-spec", default="PV1-19.1", help="Field spec for visit number.")
@click.option("--ext", default=".hl7,.txt,.dat", help="Comma-separated file extensions.")
@click.option("--integrity", is_flag=True, help="Show per-encounter admit/discharge table.")
@click.option("--timeline", "timeline_arg", default=None,
              help="Dump ordered events for a MRN (mrn:VALUE) or encounter (enc:VALUE).")
@click.option("--format", "fmt", type=click.Choice(["table", "csv", "json"]), default="table")
@click.option("--out", default=None, help="Write output to file instead of stdout.")
def encounters(path, encounter_key, mrn_spec, account_spec, visit_spec, ext,
               integrity, timeline_arg, fmt, out):
    """Reconstruct encounters and patients from an ADT feed."""
    result = load(path, _parse_ext(ext))
    if not result.messages:
        console.print("[red]No messages parsed.[/] Check the path and --ext.")
        sys.exit(1)
    console.print(
        f"[dim]Loaded {len(result.messages)} messages from "
        f"{result.files_read} file(s); skipped {result.skipped}.[/]"
    )

    grp = group(result.messages, encounter_key=encounter_key, mrn_spec=mrn_spec,
                account_spec=account_spec, visit_spec=visit_spec)

    if timeline_arg:
        if timeline_arg.startswith("mrn:"):
            kind, value = "MRN", timeline_arg[4:]
            df = timeline(grp, mrn=value)
        elif timeline_arg.startswith("enc:"):
            kind, value = "encounter", timeline_arg[4:]
            df = timeline(grp, encounter=value)
        else:
            console.print("[red]--timeline must be mrn:VALUE or enc:VALUE[/]")
            sys.exit(1)
        if df.empty:
            _no_timeline_match(kind, value, encounter_key=encounter_key,
                               messages=result.messages, mrn_spec=mrn_spec,
                               account_spec=account_spec, visit_spec=visit_spec)
        _emit(df, fmt, out, f"Timeline: {timeline_arg}")
        return

    if integrity:
        _emit(integrity_frame(grp), fmt, out, "Encounter integrity")
        return

    # default: headline summary
    s = summary(grp)
    df = pd.DataFrame([{"metric": k, "value": v} for k, v in s.items()])
    _emit(df, fmt, out, f"Feed summary (encounter key: {encounter_key})")


if __name__ == "__main__":
    main()

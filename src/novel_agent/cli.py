from __future__ import annotations

from pathlib import Path

import typer

from .config import AppSettings, ExportFormat, Profile, ProviderName
from .pipeline import finalize_delivery, run_pipeline
from .providers import resolve_provider
from .runtime import RunLockError, build_existing_run_context, build_run_context
from .schemas import InputType
from .utils import detect_input_type, load_local_env


app = typer.Typer(add_completion=False, help="Long-form novel analysis CLI")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    input: Path | None = typer.Option(None, "--input", exists=True, dir_okay=False, readable=True),
    profile: Profile = typer.Option(Profile.MVP, "--profile"),
    export: str = typer.Option("markdown,docx,pdf", "--export"),
    provider: ProviderName = typer.Option(ProviderName.AUTO, "--provider"),
    run_id: str | None = typer.Option(None, "--run-id"),
    force: bool = typer.Option(False, "--force", help="Re-run all stages even if outputs exist"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if input is None:
        typer.echo("Missing option '--input'.", err=True)
        raise typer.Exit(code=2)
    load_local_env()
    settings = AppSettings.for_profile(profile)
    input_type = InputType(detect_input_type(input))
    export_formats = _parse_export_formats(export)
    ctx = build_run_context(settings, str(input), run_id)
    try:
        ctx.acquire_lock()
    except RunLockError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    ctx.logger.info("Run created at %s", ctx.root_dir)
    selected_provider = resolve_provider(provider)
    try:
        outputs = run_pipeline(
            ctx=ctx,
            settings=settings,
            input_path=input,
            input_type=input_type,
            provider=selected_provider,
            export_formats=export_formats,
            profile=profile.value,
            force=force,
        )
        typer.echo(f"Run directory: {ctx.root_dir}")
        for name, path in outputs.items():
            typer.echo(f"{name}: {path}")
    finally:
        ctx.release_lock()


@app.command("finalize-delivery")
def finalize_delivery_command(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False, dir_okay=True, readable=True),
    export: str = typer.Option("markdown,docx,pdf", "--export"),
) -> None:
    load_local_env()
    settings = AppSettings.for_profile(Profile.MVP)
    ctx = build_existing_run_context(settings, run_dir)
    export_formats = _parse_export_formats(export)
    try:
        outputs = finalize_delivery(
            ctx=ctx,
            export_formats=export_formats,
        )
        typer.echo(f"Run directory: {ctx.root_dir}")
        for name, path in outputs.items():
            typer.echo(f"{name}: {path}")
    except RunLockError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _parse_export_formats(export: str) -> list[ExportFormat]:
    formats = [ExportFormat(item.strip()) for item in export.split(",") if item.strip()]
    if not formats:
        return [ExportFormat.MARKDOWN, ExportFormat.DOCX, ExportFormat.PDF]
    return formats


if __name__ == "__main__":
    app()

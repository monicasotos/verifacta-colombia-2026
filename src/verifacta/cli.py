"""CLI principal de verifacta."""
import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Verifacta Colombia 2026 — veeduría de actas E14")
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore", "hpack", "h2", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@app.command()
def download(
    dept: Annotated[str | None, typer.Option("--dept", help="Código de departamento (ej: 01 para Antioquia)")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Máximo de PDFs a descargar")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Descargas en paralelo")] = 10,
    output: Annotated[Path, typer.Option("--output", "-o", help="Directorio de descarga")] = Path("downloads"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Descarga actas E14 TRANSMISIÓN de la Registraduría."""
    _setup_logging(verbose)
    from .scraper.downloader import download_all

    dept_codes = [dept] if dept else None

    console.print(f"[bold green]Iniciando descarga[/] → {output}")
    console.print(f"  Workers: [yellow]{workers}[/] en paralelo")
    if limit:
        console.print(f"  Límite: [yellow]{limit}[/] actas")
    if dept_codes:
        console.print(f"  Departamento: [yellow]{dept_codes[0]}[/]")

    stats = asyncio.run(
        download_all(
            dept_codes=dept_codes,
            limit=limit,
            downloads_dir=output,
            workers=workers,
        )
    )

    console.print(f"\n[bold]Resultado:[/]")
    console.print(f"  ✓ Descargadas: [green]{stats['downloaded']}[/]")
    console.print(f"  → Saltadas (ya existían): [blue]{stats['skipped']}[/]")
    console.print(f"  ✗ Fallidas: [red]{stats['failed']}[/]")


@app.command()
def analyze(
    sample: Annotated[Path, typer.Option("--sample", help="Carpeta con PDFs o archivo PDF individual")],
    model: Annotated[str, typer.Option("--model", help="Modelo Gemini (ej: gemini-2.5-flash)")] = "gemini-2.5-flash",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Analiza actas E14 para detectar tachones, inconsistencias y firmas faltantes."""
    _setup_logging(verbose)
    from .analysis.detector import analyze_pdf

    pdfs = [sample] if sample.is_file() else sorted(sample.rglob("*.pdf"))
    if not pdfs:
        console.print(f"[red]No se encontraron PDFs en {sample}[/]")
        raise typer.Exit(1)

    console.print(f"[bold green]Analizando {len(pdfs)} actas[/] con {model}")

    results = {"ok": 0, "flagged": 0, "error": 0}

    async def _run():
        for pdf in pdfs:
            try:
                result = await analyze_pdf(pdf, model=model)
                if result.flagged:
                    results["flagged"] += 1
                    console.print(f"[red]⚑ ALERTA[/] {pdf.parent.name}/{pdf.name}")
                    if result.consistencia_ok is False:
                        console.print(f"  → Inconsistencia: {result.votos}")
                    if result.tachones:
                        console.print(f"  → Tachones en: {result.tachon_campos}")
                    if result.firmas_faltantes:
                        console.print(f"  → Firmas: {result.firmas_detalle}")
                else:
                    results["ok"] += 1
                    if verbose:
                        console.print(f"[green]✓[/] {pdf.name}")
            except Exception as e:
                results["error"] += 1
                logger.warning(f"Error analizando {pdf}: {e}")

    asyncio.run(_run())

    console.print(f"\n[bold]Resultado:[/]")
    console.print(f"  ✓ Sin anomalías: [green]{results['ok']}[/]")
    console.print(f"  ⚑ Con alertas:  [red]{results['flagged']}[/]")
    console.print(f"  ✗ Errores:       [yellow]{results['error']}[/]")


@app.command()
def report(
    subcommand: Annotated[str, typer.Argument(help="summary | flags")] = "summary",
    format: Annotated[str, typer.Option("--format")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Genera reportes de descargas y alertas."""
    _setup_logging(False)
    console.print("[yellow]Módulo de reportes en construcción[/]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
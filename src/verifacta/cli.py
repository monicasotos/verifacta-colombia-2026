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
    for noisy in ("httpx", "httpcore", "hpack", "h2", "asyncio",
                  "google", "google.ai", "google.genai", "google.genai.client",
                  "google.ai.generativelanguage"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@app.command()
def download(
    dept: Annotated[str | None, typer.Option("--dept", help="Código de departamento (ej: 01 para Antioquia)")] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Máximo de PDFs a descargar")] = None,
    workers: Annotated[int, typer.Option("--workers", "-w", help="Descargas en paralelo (máx 3-5 para evitar bloqueo)")] = 3,
    delay: Annotated[float, typer.Option("--delay", help="Segundos entre requests por worker")] = 0.5,
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
            delay=delay,
        )
    )

    console.print(f"\n[bold]Resultado:[/]")
    console.print(f"  ✓ Descargadas: [green]{stats['downloaded']}[/]")
    console.print(f"  → Saltadas (ya existían): [blue]{stats['skipped']}[/]")
    console.print(f"  ✗ Fallidas: [red]{stats['failed']}[/]")


@app.command()
def analyze(
    sample: Annotated[Path | None, typer.Option("--sample", help="Carpeta con PDFs o archivo PDF individual")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", "-f", help="Archivo con rutas de PDFs (una por línea)")] = None,
    model: Annotated[str, typer.Option("--model", help="Modelo Gemini (ej: gemini-2.5-flash)")] = "gemini-2.5-flash",
    db: Annotated[Path, typer.Option("--db", help="Base de datos SQLite")] = Path("results/verifacta.db"),
    workers: Annotated[int, typer.Option("--workers", "-w", help="Análisis en paralelo")] = 5,
    skip_analyzed: Annotated[bool, typer.Option("--skip-analyzed/--reanalyze", help="Saltar actas ya analizadas")] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Analiza actas E14 para detectar tachones, inconsistencias y firmas faltantes."""
    _setup_logging(verbose)
    from .analysis.detector import analyze_pdf
    from .storage.repository import Repository

    if from_file:
        pdfs = [Path(p.strip()) for p in from_file.read_text().splitlines() if p.strip()]
    elif sample:
        pdfs = [sample] if sample.is_file() else sorted(sample.rglob("*.pdf"))
    else:
        console.print("[red]Usa --sample <carpeta> o --from-file <archivo>[/]")
        raise typer.Exit(1)

    if not pdfs:
        console.print(f"[red]No se encontraron PDFs en {sample}[/]")
        raise typer.Exit(1)

    repo = Repository(db)
    if skip_analyzed:
        pdfs = [p for p in pdfs if not repo.already_analyzed(p)]
        if not pdfs:
            console.print("[green]Todas las actas ya están analizadas.[/]")
            return

    console.print(f"[bold green]Analizando {len(pdfs)} actas[/] con {model}")

    stats = {"ok": 0, "flagged": 0, "error": 0}
    semaphore = asyncio.Semaphore(workers)
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

    async def _analyze_one(pdf: Path, progress, task) -> None:
        async with semaphore:
            try:
                result = await analyze_pdf(pdf, model=model)
                repo.save_analysis(pdf, result, modelo=model)
                if result.flagged:
                    stats["flagged"] += 1
                    progress.print(f"[red]⚑[/] {pdf.parent.name}")
                    if result.consistencia_ok is False:
                        progress.print(f"   Inconsistencia: {result.votos}")
                    if result.tachones:
                        progress.print(f"   Tachones en: {result.tachon_campos}")
                    if result.firmas_faltantes:
                        progress.print(f"   Firmas: {result.firmas_detalle}")
                else:
                    stats["ok"] += 1
                    if verbose:
                        progress.print(f"[green]✓[/] {pdf.parent.name}")
            except Exception as e:
                stats["error"] += 1
                progress.print(f"[yellow]✗[/] {pdf.name}: {e}")
            finally:
                progress.advance(task)

    async def _run():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Analizando ({workers} workers)...", total=len(pdfs))
            await asyncio.gather(*[_analyze_one(pdf, progress, task) for pdf in pdfs])

    asyncio.run(_run())

    console.print(f"\n[bold]Resultado:[/]")
    console.print(f"  ✓ Sin anomalías: [green]{stats['ok']}[/]")
    console.print(f"  ⚑ Con alertas:  [red]{stats['flagged']}[/]")
    console.print(f"  ✗ Errores:       [yellow]{stats['error']}[/]")
    console.print(f"  Guardado en: [dim]{db}[/]")


@app.command()
def sample(
    depts: Annotated[Path, typer.Option("--depts", help="JSON de departamentos de interés")] = Path("departamentos_de_interes.json"),
    n: Annotated[int, typer.Option("--n", help="Tamaño de la muestra")] = 1000,
    downloads: Annotated[Path, typer.Option("--downloads", help="Carpeta de descargas")] = Path("downloads"),
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Archivo de salida con rutas (una por línea)")] = None,
    seed: Annotated[int, typer.Option("--seed", help="Semilla aleatoria para reproducibilidad")] = 42,
) -> None:
    """Selecciona una muestra proporcional de actas para analizar."""
    _setup_logging(False)
    from .scraper.sampler import build_sample_from_downloads, load_dept_names

    if not depts.exists():
        console.print(f"[red]No se encontró {depts}[/]")
        raise typer.Exit(1)

    dept_names = load_dept_names(depts)
    console.print(f"[bold green]Muestreando[/] {n} actas de {len(dept_names)} departamentos")

    paths = build_sample_from_downloads(downloads, dept_names, n=n, seed=seed)

    if not paths:
        console.print("[red]No se encontraron actas descargadas para esos departamentos.[/]")
        raise typer.Exit(1)

    if output:
        output.write_text("\n".join(str(p) for p in paths))
        console.print(f"  → {len(paths)} rutas guardadas en [yellow]{output}[/]")
    else:
        for p in paths:
            console.print(str(p))

    console.print(f"\n[bold]{len(paths)} actas seleccionadas[/] (seed={seed})")


@app.command()
def report(
    subcommand: Annotated[str, typer.Argument(help="summary | flags")] = "summary",
    db: Annotated[Path, typer.Option("--db")] = Path("results/verifacta.db"),
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Exportar a CSV")] = None,
    severidad: Annotated[str | None, typer.Option("--severidad", "-s", help="Filtrar por severidad: grave | moderado | leve")] = None,
) -> None:
    """Muestra resumen de análisis o lista de actas flaggeadas."""
    _setup_logging(False)
    from .storage.repository import Repository

    if not db.exists():
        console.print(f"[red]No existe la base de datos {db}. Corre primero 'analyze'.[/]")
        raise typer.Exit(1)

    repo = Repository(db)

    if subcommand == "summary":
        s = repo.summary()
        console.print(f"\n[bold]Resumen del análisis[/]")
        console.print(f"  Actas analizadas:    [white]{s['total']}[/]")
        console.print(f"  Con alguna alerta:   [red]{s['flagged']}[/]")
        console.print(f"    ↳ Graves:          [red]{s['graves']}[/]")
        console.print(f"    ↳ Moderados:       [yellow]{s['moderados']}[/]")
        console.print(f"    ↳ Leves:           [blue]{s['leves']}[/]")
        console.print(f"  Inconsistencia suma: [red]{s['inconsistentes']}[/]")
        console.print(f"  Tachones:            [red]{s['tachones']}[/]")
        console.print(f"  Firmas faltantes:    [red]{s['firmas_faltantes']}[/]")

    elif subcommand == "flags":
        records = repo.flagged_records(severidad=severidad)
        if not records:
            msg = f"Sin alertas{f' de severidad {severidad!r}' if severidad else ''}."
            console.print(f"[green]{msg}[/]")
            return

        SEVERITY_COLOR = {"grave": "red", "moderado": "yellow", "leve": "blue"}

        if output:
            import csv
            with open(output, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["dept", "muni", "zona", "puesto", "mesa", "severidad",
                            "consistencia_ok", "tachones", "tachon_campos",
                            "firmas_faltantes", "firmas_detalle", "pdf_path"])
                for r in records:
                    w.writerow([r.dept, r.muni_code, r.zona, r.puesto, r.mesa, r.severidad,
                                r.consistencia_ok, r.tachones, r.tachon_campos,
                                r.firmas_faltantes, r.firmas_detalle, r.pdf_path])
            console.print(f"[green]{len(records)} alertas exportadas a {output}[/]")
        else:
            title = f"Actas con alertas ({len(records)})"
            if severidad:
                title += f" — severidad: {severidad}"
            table = Table(title=title)
            table.add_column("Severidad"); table.add_column("Dept")
            table.add_column("Muni"); table.add_column("Mesa")
            table.add_column("Inconsistente"); table.add_column("Tachones"); table.add_column("Firmas")
            for r in records:
                color = SEVERITY_COLOR.get(r.severidad or "", "white")
                table.add_row(
                    f"[{color}]{r.severidad or '?'}[/]",
                    r.dept or "", r.muni_code or "", r.mesa or "",
                    "✗" if r.consistencia_ok is False else "✓",
                    "⚑" if r.tachones else "–",
                    "⚑" if r.firmas_faltantes else "–",
                )
            console.print(table)


@app.command()
def cleanup(
    downloads: Annotated[Path, typer.Option("--downloads", help="Carpeta de descargas")] = Path("downloads"),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Solo mostrar, no borrar")] = False,
) -> None:
    """Detecta y elimina PDFs corruptos (HTML disfrazado de PDF) para re-descarga."""
    _setup_logging(False)
    import subprocess

    console.print(f"[bold]Escaneando {downloads} en busca de archivos corruptos...[/]")

    corrupted = []
    for pdf in downloads.rglob("*.pdf"):
        try:
            header = pdf.read_bytes()[:5]
            if not header.startswith(b"%PDF"):
                corrupted.append(pdf)
        except Exception:
            corrupted.append(pdf)

    console.print(f"  Archivos corruptos encontrados: [red]{len(corrupted):,}[/]")

    if not corrupted:
        console.print("[green]Todo limpio.[/]")
        return

    if dry_run:
        console.print("[yellow]Modo dry-run — no se borra nada.[/]")
        for p in corrupted[:10]:
            console.print(f"  {p}")
        if len(corrupted) > 10:
            console.print(f"  ... y {len(corrupted) - 10} más")
        return

    for pdf in corrupted:
        pdf.unlink()
        # Borrar carpeta si quedó vacía
        if not any(pdf.parent.iterdir()):
            pdf.parent.rmdir()

    console.print(f"[green]Eliminados {len(corrupted):,} archivos corruptos.[/] Vuelve a correr 'download' para re-descargarlos.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
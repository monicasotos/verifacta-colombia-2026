"""
Orquesta la descarga de actas E14 TRANSMISIÓN.

Fuente: JSON estático allTransmissionCodes.json (~36MB, ~122k actas).
Prioridad: departamentos ordenados por población (mayor a menor).
Skip idempotente: si el archivo ya existe, no re-descarga.
"""
import asyncio
import logging
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .client import RegistraduriaClient

logger = logging.getLogger(__name__)

DOWNLOADS_DIR = Path("downloads")

# Códigos internos de la API Registraduría (NO son códigos DANE)
DEPT_PRIORITY = [
    "16",  # BOGOTA D.C.
    "01",  # ANTIOQUIA
    "31",  # VALLE
    "15",  # CUNDINAMARCA
    "03",  # ATLANTICO
    "05",  # BOLIVAR
    "27",  # SANTANDER
    "23",  # NARIÑO
    "13",  # CORDOBA
    "11",  # CAUCA
    "09",  # CALDAS
    "25",  # NORTE DE SANTANDER
    "07",  # BOYACA
    "12",  # CESAR
    "28",  # SUCRE
    "19",  # HUILA
    "52",  # META
    "26",  # QUINDIO
    "24",  # RISARALDA
    "44",  # CAQUETA
    "21",  # MAGDALENA
    "29",  # TOLIMA
    "48",  # LA GUAJIRA
    "17",  # CHOCO
    "46",  # CASANARE
    "64",  # PUTUMAYO
    "40",  # ARAUCA
    "50",  # GUAINIA
    "54",  # GUAVIARE
    "56",  # SAN ANDRES
    "60",  # AMAZONAS
    "68",  # VAUPES
    "72",  # VICHADA
    "88",  # CONSULADOS
]


def _pdf_path(node: dict) -> str:
    """Construye el path relativo del PDF desde los campos del nodo."""
    dept = node["idDepartmentCode"]
    muni = node["municipalityCode"]
    zona = node["idZoneCode"].zfill(3)
    puesto = node["standCode"]
    mesa = str(node["numberStand"]).zfill(3)
    filename = node["expectedName"]
    return f"{dept}/{muni}/{zona}/{puesto}/{mesa}/PRE/{filename}"


def _folder_name(dept_nombre: str, node: dict) -> str:
    """Nombre de carpeta: {DEPT}_{MUNI}_Z{ZONA}_P{PUESTO}_M{MESA}."""
    muni = node["municipalityCode"]
    zona = node["idZoneCode"].zfill(2)
    puesto = node["standCode"].zfill(2)
    mesa = str(node["numberStand"]).lstrip("0") or "0"
    return f"{dept_nombre}_{muni}_Z{zona}_P{puesto}_M{mesa}"


async def download_all(
    dept_codes: list[str] | None = None,
    limit: int | None = None,
    downloads_dir: Path = DOWNLOADS_DIR,
    workers: int = 10,
) -> dict:
    """
    Descarga todas las actas TRANSMISIÓN disponibles en paralelo.

    Args:
        dept_codes: Códigos de departamento a descargar. None = todos en orden de población.
        limit: Máximo de PDFs a descargar (para pruebas).
        downloads_dir: Directorio donde guardar los PDFs.
        workers: Número de descargas concurrentes.

    Returns:
        dict con stats: downloaded, skipped, failed.
    """
    downloads_dir.mkdir(parents=True, exist_ok=True)
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    semaphore = asyncio.Semaphore(workers)

    async with RegistraduriaClient() as client:
        logger.info("Cargando catálogo de departamentos...")
        all_depts = await client.get_departments()
        dept_map = {d["idDepartmentCode"]: d["departmentName"] for d in all_depts}

        logger.info("Cargando catálogo de actas (~36MB)...")
        codes = await client.get_all_transmission_codes()
        all_nodes = codes["status11"]
        logger.info(f"Total actas disponibles: {len(all_nodes):,}")

        if dept_codes:
            ordered_depts = [d for d in dept_codes if d in dept_map]
        else:
            seen: set[str] = set()
            ordered_depts = []
            for code in DEPT_PRIORITY:
                if code in dept_map and code not in seen:
                    ordered_depts.append(code)
                    seen.add(code)
            for code in dept_map:
                if code not in seen:
                    ordered_depts.append(code)

        nodes_by_dept: dict[str, list[dict]] = {}
        for node in all_nodes:
            dc = node["idDepartmentCode"]
            nodes_by_dept.setdefault(dc, []).append(node)

        async def _download_node(node: dict, dept_nombre: str) -> str:
            filename = node.get("expectedName", "")
            if not filename:
                return "failed"

            dest_file = downloads_dir / _folder_name(dept_nombre, node) / filename
            if dest_file.exists():
                return "skipped"

            try:
                async with semaphore:
                    pdf_bytes = await client.download_pdf(_pdf_path(node))
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(pdf_bytes)
                logger.debug(f"✓ {dest_file}")
                return "downloaded"
            except Exception as e:
                logger.warning(f"✗ {filename}: {e}")
                return "failed"

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress:
            dept_task = progress.add_task("Departamentos", total=len(ordered_depts))

            for dept_code in ordered_depts:
                dept_nombre = dept_map.get(dept_code, dept_code)
                progress.update(dept_task, description=f"[bold blue]{dept_nombre}")

                dept_nodes = nodes_by_dept.get(dept_code, [])
                if not dept_nodes:
                    progress.advance(dept_task)
                    continue

                # Aplicar límite antes de crear tareas
                if limit:
                    done = stats["downloaded"] + stats["skipped"]
                    remaining = limit - done
                    if remaining <= 0:
                        return stats
                    dept_nodes = dept_nodes[:remaining]

                mesa_task = progress.add_task(f"  {dept_nombre}", total=len(dept_nodes))

                # Lanzar todas las descargas del departamento en paralelo
                tasks = [
                    asyncio.create_task(_download_node(node, dept_nombre))
                    for node in dept_nodes
                ]
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    stats[result] += 1
                    progress.advance(mesa_task)

                progress.advance(dept_task)

    return stats
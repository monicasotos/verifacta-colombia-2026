"""
Descarga y persiste en disco los PDFs de decretos ya indexados en el
repositorio (requiere haber corrido `sync-mes`/`sync` antes — este módulo
solo baja el archivo y actualiza `path_local`).

Convención de carpeta: decretos/{presidente_slug}/{anio}/{numero}.pdf
Skip idempotente: si el archivo ya existe en disco, no se re-descarga.
"""
import asyncio
import logging
from pathlib import Path

from .client import DecretosClient
from .repository import DecretoRecord, DecretosRepository

logger = logging.getLogger(__name__)

DECRETOS_DIR = Path("decretos")


def dest_path(record: DecretoRecord, base_dir: Path = DECRETOS_DIR) -> Path:
    presidente = record.presidente_slug or "sin-presidente"
    return base_dir / presidente / str(record.anio) / f"{record.numero}.pdf"


async def download_all(
    repo: DecretosRepository,
    base_dir: Path = DECRETOS_DIR,
    workers: int = 3,
    presidente_slug: str | None = None,
    limit: int | None = None,
) -> dict:
    """
    Descarga los PDFs de los decretos en `repo` que todavía no tienen
    `path_local`. Retorna stats: downloaded, skipped, failed.
    """
    pendientes = [r for r in repo.pendientes_de_descarga(presidente_slug) if r.url_pdf]
    if limit:
        pendientes = pendientes[:limit]

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    if not pendientes:
        return stats

    semaphore = asyncio.Semaphore(workers)

    async with DecretosClient() as client:
        # El challenge de F5 se pasa navegando una página real; hacerlo una
        # sola vez aquí establece las cookies de sesión que luego reusan
        # todas las descargas en paralelo vía context.request.
        primero = pendientes[0]
        await client.fetch_month(primero.fecha_firma.year, primero.fecha_firma.month)

        async def _download_one(record: DecretoRecord) -> None:
            dest = dest_path(record, base_dir)
            if dest.exists():
                repo.set_path_local(record.anio, record.numero, str(dest))
                stats["skipped"] += 1
                return
            try:
                async with semaphore:
                    content = await client.download_pdf(record.url_pdf)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                repo.set_path_local(record.anio, record.numero, str(dest))
                stats["downloaded"] += 1
            except Exception as e:
                logger.warning(f"Fallo descargando decreto {record.anio}-{record.numero}: {e}")
                stats["failed"] += 1

        await asyncio.gather(*[_download_one(r) for r in pendientes])

    return stats

"""Orquesta: cliente -> mapeo a presidente -> persistencia."""
import logging

from .client import DecretosClient
from .models import Decreto
from .presidentes import presidente_para_fecha
from .repository import DecretosRepository

logger = logging.getLogger(__name__)


def _to_decretos(raw: list[dict]) -> list[Decreto]:
    decretos = []
    for r in raw:
        presidente = presidente_para_fecha(r["fecha_firma"])
        decretos.append(Decreto(
            anio=r["anio"],
            numero=r["numero"],
            fecha_firma=r["fecha_firma"],
            titulo=r["titulo"],
            presidente_slug=presidente.slug if presidente else None,
            url_pdf=r["url_pdf"],
        ))
    return decretos


async def sync_months(client: DecretosClient, months: list[tuple[int, int]], repo: DecretosRepository) -> dict:
    """
    Sincroniza varios meses reusando la misma sesión de Playwright — mucho
    más eficiente que abrir un browser nuevo por mes cuando se barre un
    periodo presidencial completo.
    """
    totals = {"creados": 0, "actualizados": 0}
    for year, month in months:
        raw = await client.fetch_month(year, month)
        decretos = _to_decretos(raw)
        sin_presidente = sum(1 for d in decretos if d.presidente_slug is None)
        if sin_presidente:
            logger.warning(f"{sin_presidente} decretos de {month}/{year} no mapean a ningún periodo presidencial conocido")
        stats = repo.upsert_many(decretos)
        totals["creados"] += stats["creados"]
        totals["actualizados"] += stats["actualizados"]
    return totals


async def sync_month(year: int, month: int, repo: DecretosRepository) -> dict:
    """Descarga la metadata de un solo mes/año (abre y cierra su propio browser)."""
    async with DecretosClient() as client:
        return await sync_months(client, [(year, month)], repo)

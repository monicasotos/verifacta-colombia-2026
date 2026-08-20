"""
Periodos presidenciales de interés y mapeo fecha de firma -> presidente.

Fecha de posesión constitucional en Colombia: 7 de agosto. `fecha_fin` es la
fecha de posesión del sucesor (exclusiva), no el último día en funciones.

NOTA: la fecha de posesión de Abelardo de la Espriella (2026-08-07) es una
asunción basada en la fecha constitucional estándar — ajustar si se confirma
una fecha distinta. Mientras no haya decretos suyos publicados en la fuente,
el pipeline simplemente no encuentra nada para ese presidente (no es un error).
"""
from datetime import date

from .models import Presidente

PRESIDENTES: list[Presidente] = [
    Presidente(
        slug="duque",
        nombre="Iván Duque",
        fecha_inicio=date(2018, 8, 7),
        fecha_fin=date(2022, 8, 7),
    ),
    Presidente(
        slug="petro",
        nombre="Gustavo Petro",
        fecha_inicio=date(2022, 8, 7),
        fecha_fin=date(2026, 8, 7),
    ),
    Presidente(
        slug="de-la-espriella",
        nombre="Abelardo de la Espriella",
        fecha_inicio=date(2026, 8, 7),
        fecha_fin=None,
    ),
]

_POR_SLUG = {p.slug: p for p in PRESIDENTES}


def presidente_para_fecha(fecha: date) -> Presidente | None:
    """Retorna el presidente en funciones en `fecha`, o None si no hay periodo definido."""
    for p in PRESIDENTES:
        if fecha < p.fecha_inicio:
            continue
        if p.fecha_fin is not None and fecha >= p.fecha_fin:
            continue
        return p
    return None


def presidente_por_slug(slug: str) -> Presidente:
    try:
        return _POR_SLUG[slug]
    except KeyError:
        raise ValueError(f"Presidente desconocido: {slug!r}. Opciones: {list(_POR_SLUG)}")


def meses_del_periodo(
    presidente: Presidente, hasta: date | None = None, mas_reciente_primero: bool = True,
) -> list[tuple[int, int]]:
    """
    Genera pares (año, mes) del periodo, desde el inicio hasta el fin (o
    `hasta`, para no pedir meses futuros que la fuente aún no publicó).

    Por defecto retorna del más reciente al más antiguo: al descargar, nos
    importa más ver primero los decretos recientes que barrer todo el
    histórico en orden cronológico — así una corrida parcial (o con
    `--limit`) ya deja lo más útil descargado.

    Si el periodo empieza después de `hasta` (ej. un presidente que todavía
    no toma posesión), retorna lista vacía en vez de fallar.
    """
    fin = presidente.fecha_fin or hasta or date.today()
    fin = min(fin, hasta) if hasta else fin
    inicio = presidente.fecha_inicio
    if inicio > fin:
        return []

    meses = []
    anio, mes = inicio.year, inicio.month
    while (anio, mes) <= (fin.year, fin.month):
        meses.append((anio, mes))
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    return list(reversed(meses)) if mas_reciente_primero else meses

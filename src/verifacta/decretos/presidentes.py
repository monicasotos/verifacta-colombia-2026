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

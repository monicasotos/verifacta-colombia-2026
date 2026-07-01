"""
Muestreo estratificado de actas E14 descargadas para análisis.

Estrategia: proporcional al número de mesas por municipio dentro de los
departamentos de interés. Los municipios más grandes (más mesas) aportan
más actas a la muestra.
"""
import json
import random
import re
from collections import defaultdict
from pathlib import Path


def _muni_key(folder_name: str) -> str:
    """Extrae '{DEPT}_{MUNI}' del nombre de carpeta '{DEPT}_{MUNI}_Z{z}_P{p}_M{m}'."""
    # Busca el patrón _Z seguido de dígitos para saber dónde termina el prefijo
    m = re.search(r"_Z\d+_P\d+_M\d+$", folder_name)
    if m:
        return folder_name[: m.start()]
    return folder_name


def _dept_name(folder_name: str) -> str:
    """Extrae el nombre del departamento (primer segmento antes del código de municipio)."""
    # El código de municipio es siempre numérico; el nombre del dpto puede tener espacios/puntos
    parts = folder_name.split("_")
    # Busca el primer segmento que sea puramente numérico — ese es el muni code
    for i, part in enumerate(parts):
        if part.isdigit():
            return "_".join(parts[:i])
    return parts[0]


def build_sample_from_downloads(
    downloads_dir: Path,
    dept_names: list[str],
    n: int,
    seed: int | None = 42,
) -> list[Path]:
    """
    Selecciona una muestra proporcional de PDFs ya descargados.

    Args:
        downloads_dir: Carpeta raíz de descargas.
        dept_names: Lista de nombres de departamento a incluir (ej: ["ANTIOQUIA", "TOLIMA"]).
        n: Tamaño total de la muestra.
        seed: Semilla para reproducibilidad.

    Returns:
        Lista de rutas a PDFs seleccionados.
    """
    rng = random.Random(seed)
    dept_set = {d.upper() for d in dept_names}

    # Agrupar PDFs por municipio (clave: DEPT_MUNI)
    by_muni: dict[str, list[Path]] = defaultdict(list)
    for folder in downloads_dir.iterdir():
        if not folder.is_dir():
            continue
        dept = _dept_name(folder.name)
        if dept not in dept_set:
            continue
        key = _muni_key(folder.name)
        by_muni[key].extend(folder.glob("*.pdf"))

    if not by_muni:
        return []

    total_pool = sum(len(v) for v in by_muni.values())
    if n >= total_pool:
        all_pdfs = [p for pdfs in by_muni.values() for p in pdfs]
        rng.shuffle(all_pdfs)
        return all_pdfs

    # Cuotas proporcionales al tamaño de cada municipio
    munis = sorted(by_muni.keys(), key=lambda k: -len(by_muni[k]))
    sample: list[Path] = []
    remaining = n
    pool_left = total_pool

    for key in munis:
        if remaining <= 0:
            break
        pdfs = by_muni[key]
        quota = max(1, round(remaining * len(pdfs) / pool_left))
        quota = min(quota, remaining, len(pdfs))
        sample.extend(rng.sample(pdfs, quota))
        remaining -= quota
        pool_left -= len(pdfs)

    return sample


def load_dept_names(depts_file: Path) -> list[str]:
    """Carga nombres de departamento desde un JSON con estructura {nodes: [{departmentName, ...}]}."""
    data = json.loads(depts_file.read_text())
    return [node["departmentName"] for node in data["nodes"]]

a"""
Muestreo estratificado de actas E14 para análisis.

Estrategia: top-N municipios por número de mesas (proxy de población),
muestra proporcional aleatoria dentro de cada uno.
"""
import random
from collections import Counter, defaultdict


def build_sample(
    nodes: list[dict],
    n: int,
    top_munis: int = 100,
    seed: int | None = 42,
) -> list[dict]:
    """
    Retorna una muestra de n nodos priorizando los municipios más grandes.

    Args:
        nodes: Lista de nodos status11 del allTransmissionCodes.json.
        n: Tamaño de la muestra.
        top_munis: Cuántos municipios más grandes incluir (por número de mesas).
        seed: Semilla para reproducibilidad. None = aleatorio puro.

    Returns:
        Lista de n nodos seleccionados proporcionalmente.
    """
    rng = random.Random(seed)

    # Agrupar nodos por (dept, municipio)
    by_muni: dict[tuple, list[dict]] = defaultdict(list)
    for node in nodes:
        key = (node["idDepartmentCode"], node["municipalityCode"])
        by_muni[key].append(node)

    # Seleccionar top-N municipios por número de mesas
    muni_sizes = Counter({k: len(v) for k, v in by_muni.items()})
    selected_munis = {k for k, _ in muni_sizes.most_common(top_munis)}

    # Pool filtrado
    pool: dict[tuple, list[dict]] = {k: v for k, v in by_muni.items() if k in selected_munis}
    total_in_pool = sum(len(v) for v in pool.values())

    if n >= total_in_pool:
        # Piden más de lo que hay — devolver todo el pool mezclado
        all_nodes = [node for nodes_list in pool.values() for node in nodes_list]
        rng.shuffle(all_nodes)
        return all_nodes

    # Asignar cuotas proporcionales al tamaño de cada municipio
    sample: list[dict] = []
    remaining = n
    munis_sorted = sorted(pool.keys(), key=lambda k: -len(pool[k]))

    for i, key in enumerate(munis_sorted):
        muni_nodes = pool[key]
        munis_left = len(munis_sorted) - i
        # Cuota proporcional, garantizando al menos 1 por municipio
        quota = max(1, round(remaining * len(muni_nodes) / total_in_pool))
        quota = min(quota, remaining - (munis_left - 1), len(muni_nodes))
        sample.extend(rng.sample(muni_nodes, quota))
        remaining -= quota
        total_in_pool -= len(muni_nodes)
        if remaining <= 0:
            break

    return sample
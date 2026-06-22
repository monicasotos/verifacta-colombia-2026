"""
HTTP client para la Registraduría Nacional.

Fuentes de datos (todas estáticas, sin auth):
- JSON: departamentos, corporaciones, códigos de transmisión
- PDF: /assets/temis/pdf/{dept}/{muni}/{zona}/{puesto}/{mesa}/PRE/{hash}.pdf
"""
import logging
import uuid  # usado en download_pdf y get_all_transmission_codes

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://e14segundavueltapresidente.registraduria.gov.co"
ASSETS_BASE = f"{BASE_URL}/assets/temis"
DIVIPOL_BASE = f"{ASSETS_BASE}/divipol_json"


class RegistraduriaClient:
    """Cliente async para la API estática de la Registraduría."""

    def __init__(self, rate_limit: float = 2.0):
        self._rate_limit = rate_limit
        self._http = httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            follow_redirects=True,
            timeout=60.0,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()

    async def get_departments(self) -> list[dict]:
        """Retorna lista de departamentos (hardcodeada — la API bloquea requests automáticas)."""
        return [
            {"idDepartmentCode": "01", "departmentName": "ANTIOQUIA"},
            {"idDepartmentCode": "03", "departmentName": "ATLANTICO"},
            {"idDepartmentCode": "05", "departmentName": "BOLIVAR"},
            {"idDepartmentCode": "07", "departmentName": "BOYACA"},
            {"idDepartmentCode": "09", "departmentName": "CALDAS"},
            {"idDepartmentCode": "11", "departmentName": "CAUCA"},
            {"idDepartmentCode": "12", "departmentName": "CESAR"},
            {"idDepartmentCode": "13", "departmentName": "CORDOBA"},
            {"idDepartmentCode": "15", "departmentName": "CUNDINAMARCA"},
            {"idDepartmentCode": "16", "departmentName": "BOGOTA D.C."},
            {"idDepartmentCode": "17", "departmentName": "CHOCO"},
            {"idDepartmentCode": "19", "departmentName": "HUILA"},
            {"idDepartmentCode": "21", "departmentName": "MAGDALENA"},
            {"idDepartmentCode": "23", "departmentName": "NARIÑO"},
            {"idDepartmentCode": "24", "departmentName": "RISARALDA"},
            {"idDepartmentCode": "25", "departmentName": "NORTE DE SANTANDER"},
            {"idDepartmentCode": "26", "departmentName": "QUINDIO"},
            {"idDepartmentCode": "27", "departmentName": "SANTANDER"},
            {"idDepartmentCode": "28", "departmentName": "SUCRE"},
            {"idDepartmentCode": "29", "departmentName": "TOLIMA"},
            {"idDepartmentCode": "31", "departmentName": "VALLE"},
            {"idDepartmentCode": "40", "departmentName": "ARAUCA"},
            {"idDepartmentCode": "44", "departmentName": "CAQUETA"},
            {"idDepartmentCode": "46", "departmentName": "CASANARE"},
            {"idDepartmentCode": "48", "departmentName": "LA GUAJIRA"},
            {"idDepartmentCode": "50", "departmentName": "GUAINIA"},
            {"idDepartmentCode": "52", "departmentName": "META"},
            {"idDepartmentCode": "54", "departmentName": "GUAVIARE"},
            {"idDepartmentCode": "56", "departmentName": "SAN ANDRES"},
            {"idDepartmentCode": "60", "departmentName": "AMAZONAS"},
            {"idDepartmentCode": "64", "departmentName": "PUTUMAYO"},
            {"idDepartmentCode": "68", "departmentName": "VAUPES"},
            {"idDepartmentCode": "72", "departmentName": "VICHADA"},
            {"idDepartmentCode": "88", "departmentName": "CONSULADOS"},
        ]

    async def get_all_transmission_codes(self, cache_path: str = "scripts/allTransmissionCodes.json") -> dict[str, list[dict]]:
        """
        Carga los códigos de transmisión (~36MB, ~122k actas).

        Usa cache local si existe; si no, descarga y guarda.
        Retorna dict con claves 'status3' y 'status11'.
        """
        import json
        from pathlib import Path

        local = Path(cache_path)
        if local.exists():
            logger.info(f"Cargando códigos desde caché local: {local}")
            raw = json.loads(local.read_bytes())
        else:
            logger.info("Descargando allTransmissionCodes.json (~36MB)...")
            url = f"{DIVIPOL_BASE}/allTransmissionCodes.json"
            resp = await self._http.get(url, params={"uuid": str(uuid.uuid4())})
            resp.raise_for_status()
            content = resp.content
            if content[:5] == b"<!doc":
                raise ValueError("CDN devolvió HTML en vez del JSON — reintenta más tarde")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(content)
            raw = json.loads(content)

        data = raw["data"]
        return {
            "status3": data.get("status3", {}).get("nodes", []),
            "status11": data.get("status11", {}).get("nodes", []),
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def download_pdf(self, file_path: str) -> bytes:
        """
        Descarga un PDF dado su path relativo.

        file_path: e.g. "01/280/03/02/001/PRE/54cec...pdf"
        """
        url = f"{ASSETS_BASE}/pdf/{file_path}"
        resp = await self._http.get(url, params={"uuid": str(uuid.uuid4())})
        resp.raise_for_status()
        return resp.content
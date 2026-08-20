"""
Cliente para descargar metadata de decretos desde dapre.presidencia.gov.co.

El sitio está protegido por F5 Bot Defense (cookies TS*, challenge JS
ofuscado); un cliente HTTP plano (httpx/curl) recibe solo el script del
challenge. Confirmado en el spike (ver docs/decretos/PLAN.md) que un
Chromium real vía Playwright sí lo pasa de forma consistente.

Patrón de URL confirmado (determinístico, sin necesidad de buscar/paginar):

    https://dapre.presidencia.gov.co/normativa/decretos-{año}/decretos-{mes}-{año}

Cada entrada de decreto vive en un `<li class="dfwp-item">` con un link al
PDF (número + fecha en el texto del link) y un `<div class="description">`
con el título/asunto.
"""
import logging
import re
from datetime import date

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://dapre.presidencia.gov.co/normativa"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}
_MESES_A_NUMERO = {nombre: numero for numero, nombre in MESES_ES.items()}

_DECRETO_RE = re.compile(
    r"DECRETO\s+(?:No\.?\s*)?(\d+)\s+DEL\s+(\d{1,2})\s+DE\s+([A-ZÑÁÉÍÓÚ]+)\s+DE\s+(\d{4})",
    re.IGNORECASE,
)


def month_url(year: int, month: int) -> str:
    """URL de la página de decretos de un mes/año dado."""
    return f"{BASE_URL}/decretos-{year}/decretos-{MESES_ES[month]}-{year}"


def parse_decretos_html(html: str) -> list[dict]:
    """
    Parsea el HTML ya renderizado (post-challenge) de una página
    `decretos-{mes}-{año}` y retorna metadata cruda por decreto.

    Función pura, sin red — testeable con fixtures de HTML real.

    Retorna lista de dicts con: numero, anio, fecha_firma, titulo, url_pdf.
    Ignora entradas que no matcheen el patrón "DECRETO N DEL D DE MES DE AAAA"
    (ej. links de boilerplate del sitio, como la política de atención).
    """
    soup = BeautifulSoup(html, "html.parser")
    resultados = []
    for item in soup.select("li.dfwp-item"):
        link = item.select_one("a[href]")
        if link is None:
            continue
        match = _DECRETO_RE.search(link.get_text(strip=True))
        if match is None:
            continue
        numero, dia, mes_nombre, anio = match.groups()
        mes = _MESES_A_NUMERO.get(mes_nombre.lower())
        if mes is None:
            logger.warning(f"Mes no reconocido en decreto {numero}/{anio}: {mes_nombre!r}")
            continue
        desc = item.select_one(".description")
        resultados.append({
            "numero": int(numero),
            "anio": int(anio),
            "fecha_firma": date(int(anio), mes, int(dia)),
            "titulo": desc.get_text(strip=True) if desc else "",
            "url_pdf": link["href"],
        })
    return resultados


class DecretosClient:
    """Cliente Playwright para navegar el sitio de Normativa de Presidencia."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "DecretosClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="es-CO",
        )
        return self

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def fetch_month(self, year: int, month: int) -> list[dict]:
        """
        Descarga y parsea la metadata de decretos de un mes/año dado.

        Retorna lista vacía si la página no tiene contenido todavía (ej. mes
        futuro, o presidente recién posesionado sin decretos aún) — no lanza
        error en ese caso.
        """
        url = month_url(year, month)
        assert self._context is not None, "usar dentro de 'async with DecretosClient()'"
        page = await self._context.new_page()
        try:
            logger.info(f"Descargando {url}")
            await page.goto(url, wait_until="networkidle", timeout=45000)
            html = await page.content()
        finally:
            await page.close()
        return parse_decretos_html(html)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def download_pdf(self, url: str) -> bytes:
        """
        Descarga el PDF de un decreto.

        No abre una página nueva: reusa las cookies de sesión que ya dejó
        `fetch_month` al pasar el challenge de F5 (confirmado por spike que
        `context.request` funciona directo, sin re-renderizar). Por eso
        siempre hay que llamar a `fetch_month` al menos una vez en el mismo
        cliente antes de descargar PDFs.
        """
        assert self._context is not None, "usar dentro de 'async with DecretosClient()'"
        resp = await self._context.request.get(url)
        if resp.status != 200:
            raise ValueError(f"status {resp.status} descargando {url}")
        body = await resp.body()
        if not body.startswith(b"%PDF"):
            raise ValueError(f"Contenido no es PDF (posible bloqueo del challenge) — {url}")
        return body

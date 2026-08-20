from datetime import date
from pathlib import Path

from verifacta.decretos.client import month_url, parse_decretos_html

FIXTURE = Path(__file__).parent / "fixtures" / "decretos_agosto_2018_sample.html"


class TestMonthUrl:
    def test_construye_url_con_mes_en_espanol(self):
        assert month_url(2018, 8) == (
            "https://dapre.presidencia.gov.co/normativa/decretos-2018/decretos-agosto-2018"
        )

    def test_enero_no_agosto(self):
        assert month_url(2026, 1) == (
            "https://dapre.presidencia.gov.co/normativa/decretos-2026/decretos-enero-2026"
        )


class TestParseDecretosHtml:
    def test_extrae_los_tres_decretos_reales_del_fixture(self):
        html = FIXTURE.read_text()
        resultados = parse_decretos_html(html)
        assert len(resultados) == 3

    def test_numero_fecha_y_titulo_del_primer_decreto(self):
        html = FIXTURE.read_text()
        resultados = parse_decretos_html(html)
        primero = next(r for r in resultados if r["numero"] == 1665)
        assert primero["anio"] == 2018
        assert primero["fecha_firma"] == date(2018, 8, 31)
        assert "DIANA ISABEL CARDENAS GAMBOA" in primero["titulo"]
        assert primero["url_pdf"].endswith("DECRETO 1665 DEL 31 DE AGOSTO DE 2018.pdf")

    def test_ignora_links_de_boilerplate_que_no_son_decretos(self):
        html = FIXTURE.read_text()
        resultados = parse_decretos_html(html)
        numeros = {r["numero"] for r in resultados}
        assert numeros == {1665, 1664, 1647}

    def test_pagina_vacia_retorna_lista_vacia(self):
        assert parse_decretos_html("<html><body></body></html>") == []

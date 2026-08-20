from datetime import date

import pytest

from verifacta.decretos.presidentes import presidente_para_fecha, presidente_por_slug


class TestPresidenteParaFecha:
    def test_duque_al_inicio_de_su_periodo(self):
        p = presidente_para_fecha(date(2018, 8, 7))
        assert p is not None
        assert p.slug == "duque"

    def test_duque_en_medio_de_su_periodo(self):
        p = presidente_para_fecha(date(2020, 1, 1))
        assert p is not None
        assert p.slug == "duque"

    def test_dia_de_transicion_pertenece_al_sucesor(self):
        """fecha_fin es la fecha de posesión del sucesor: ese día ya es del nuevo presidente."""
        p = presidente_para_fecha(date(2022, 8, 7))
        assert p is not None
        assert p.slug == "petro"

    def test_dia_anterior_a_la_transicion_es_del_saliente(self):
        p = presidente_para_fecha(date(2022, 8, 6))
        assert p is not None
        assert p.slug == "duque"

    def test_petro_en_medio_de_su_periodo(self):
        p = presidente_para_fecha(date(2024, 6, 15))
        assert p is not None
        assert p.slug == "petro"

    def test_de_la_espriella_periodo_en_curso_sin_fecha_fin(self):
        p = presidente_para_fecha(date(2026, 8, 10))
        assert p is not None
        assert p.slug == "de-la-espriella"

    def test_fecha_muy_lejana_en_el_futuro_sigue_dentro_del_periodo_en_curso(self):
        p = presidente_para_fecha(date(2099, 1, 1))
        assert p is not None
        assert p.slug == "de-la-espriella"

    def test_fecha_anterior_a_duque_no_mapea(self):
        p = presidente_para_fecha(date(2018, 1, 1))
        assert p is None


class TestPresidentePorSlug:
    def test_slug_valido(self):
        p = presidente_por_slug("petro")
        assert p.nombre == "Gustavo Petro"

    def test_slug_invalido_lanza_error(self):
        with pytest.raises(ValueError):
            presidente_por_slug("no-existe")

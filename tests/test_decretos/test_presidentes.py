from datetime import date

import pytest

from verifacta.decretos.models import Presidente
from verifacta.decretos.presidentes import meses_del_periodo, presidente_para_fecha, presidente_por_slug


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


class TestMesesDelPeriodo:
    def test_periodo_de_un_solo_mes(self):
        p = Presidente(slug="x", nombre="X", fecha_inicio=date(2020, 3, 5), fecha_fin=date(2020, 3, 20))
        assert meses_del_periodo(p) == [(2020, 3)]

    def test_por_defecto_va_del_mas_reciente_al_mas_antiguo(self):
        p = Presidente(slug="x", nombre="X", fecha_inicio=date(2020, 11, 1), fecha_fin=date(2021, 2, 1))
        assert meses_del_periodo(p) == [(2021, 2), (2021, 1), (2020, 12), (2020, 11)]

    def test_mas_reciente_primero_false_da_orden_cronologico(self):
        p = Presidente(slug="x", nombre="X", fecha_inicio=date(2020, 11, 1), fecha_fin=date(2021, 2, 1))
        assert meses_del_periodo(p, mas_reciente_primero=False) == [
            (2020, 11), (2020, 12), (2021, 1), (2021, 2),
        ]

    def test_incluye_el_mes_de_fecha_fin_transicion(self):
        """El mes de la transición se incluye entero — el mapper separa por día luego."""
        duque = Presidente(slug="duque", nombre="Duque", fecha_inicio=date(2018, 8, 7), fecha_fin=date(2022, 8, 7))
        meses = meses_del_periodo(duque)
        assert meses[0] == (2022, 8)  # más reciente primero
        assert meses[-1] == (2018, 8)
        assert len(meses) == 49  # 48 meses completos + el de transición

    def test_periodo_en_curso_se_limita_a_hasta(self):
        p = Presidente(slug="x", nombre="X", fecha_inicio=date(2026, 1, 1), fecha_fin=None)
        assert meses_del_periodo(p, hasta=date(2026, 4, 15)) == [
            (2026, 4), (2026, 3), (2026, 2), (2026, 1),
        ]

    def test_presidente_que_aun_no_toma_posesion_retorna_vacio(self):
        p = Presidente(slug="futuro", nombre="Futuro", fecha_inicio=date(2030, 1, 1), fecha_fin=None)
        assert meses_del_periodo(p, hasta=date(2026, 1, 1)) == []

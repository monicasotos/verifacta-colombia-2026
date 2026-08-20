from datetime import date

from verifacta.decretos.models import Decreto
from verifacta.decretos.repository import DecretosRepository


def _decreto(numero=1665, anio=2018, presidente_slug="duque"):
    return Decreto(
        anio=anio,
        numero=numero,
        fecha_firma=date(anio, 8, 31),
        titulo="Por medio del cual se hace un nombramiento",
        presidente_slug=presidente_slug,
        url_pdf="https://example.com/decreto.pdf",
    )


class TestUpsertMany:
    def test_inserta_decretos_nuevos(self, tmp_path):
        repo = DecretosRepository(db_path=tmp_path / "decretos.db")
        stats = repo.upsert_many([_decreto(numero=1), _decreto(numero=2)])
        assert stats == {"creados": 2, "actualizados": 0}
        assert repo.total() == 2

    def test_reinsertar_el_mismo_anio_numero_actualiza_en_vez_de_duplicar(self, tmp_path):
        repo = DecretosRepository(db_path=tmp_path / "decretos.db")
        repo.upsert_many([_decreto(numero=1665, anio=2018)])
        stats = repo.upsert_many([_decreto(numero=1665, anio=2018, presidente_slug="petro")])
        assert stats == {"creados": 0, "actualizados": 1}
        assert repo.total() == 1

    def test_mismo_numero_distinto_anio_no_colisiona(self, tmp_path):
        """La numeración de decretos reinicia cada año — (anio, numero) es la clave."""
        repo = DecretosRepository(db_path=tmp_path / "decretos.db")
        repo.upsert_many([_decreto(numero=100, anio=2018)])
        repo.upsert_many([_decreto(numero=100, anio=2022)])
        assert repo.total() == 2


class TestCountsPorPresidente:
    def test_agrupa_por_presidente(self, tmp_path):
        repo = DecretosRepository(db_path=tmp_path / "decretos.db")
        repo.upsert_many([
            _decreto(numero=1, presidente_slug="duque"),
            _decreto(numero=2, presidente_slug="duque"),
            _decreto(numero=3, presidente_slug="petro"),
        ])
        counts = repo.counts_por_presidente()
        assert counts == {"duque": 2, "petro": 1}

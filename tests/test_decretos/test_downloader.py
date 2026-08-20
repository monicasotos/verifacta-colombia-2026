from datetime import date
from pathlib import Path

from verifacta.decretos.downloader import dest_path
from verifacta.decretos.models import Decreto
from verifacta.decretos.repository import DecretosRepository


def _record_like(anio=2018, numero=1665, presidente_slug="duque"):
    class _R:
        pass
    r = _R()
    r.anio = anio
    r.numero = numero
    r.presidente_slug = presidente_slug
    return r


class TestDestPath:
    def test_convencion_de_carpeta_por_presidente_anio_numero(self):
        p = dest_path(_record_like(), base_dir=Path("decretos"))
        assert p == Path("decretos/duque/2018/1665.pdf")

    def test_decreto_sin_presidente_mapeado_usa_carpeta_generica(self):
        p = dest_path(_record_like(presidente_slug=None), base_dir=Path("decretos"))
        assert p == Path("decretos/sin-presidente/2018/1665.pdf")


class TestPendientesDeDescarga:
    def _decreto(self, numero, presidente_slug="duque"):
        return Decreto(
            anio=2018, numero=numero, fecha_firma=date(2018, 8, 31),
            titulo="t", presidente_slug=presidente_slug,
            url_pdf="https://example.com/d.pdf",
        )

    def test_decretos_sin_path_local_estan_pendientes(self, tmp_path):
        repo = DecretosRepository(db_path=tmp_path / "d.db")
        repo.upsert_many([self._decreto(1), self._decreto(2)])
        assert len(repo.pendientes_de_descarga()) == 2

    def test_set_path_local_lo_saca_de_pendientes(self, tmp_path):
        repo = DecretosRepository(db_path=tmp_path / "d.db")
        repo.upsert_many([self._decreto(1), self._decreto(2)])
        repo.set_path_local(2018, 1, "decretos/duque/2018/1.pdf")
        pendientes = repo.pendientes_de_descarga()
        assert len(pendientes) == 1
        assert pendientes[0].numero == 2

    def test_filtra_por_presidente(self, tmp_path):
        repo = DecretosRepository(db_path=tmp_path / "d.db")
        repo.upsert_many([
            self._decreto(1, presidente_slug="duque"),
            self._decreto(2, presidente_slug="petro"),
        ])
        pendientes = repo.pendientes_de_descarga(presidente_slug="petro")
        assert len(pendientes) == 1
        assert pendientes[0].presidente_slug == "petro"

import pytest
from verifacta.scraper.models import Departamento, Municipio, Zona, Puesto, Mesa, MesaId


class TestDepartamento:
    def test_basic_fields(self):
        d = Departamento(codigo="01", nombre="ANTIOQUIA")
        assert d.codigo == "01"
        assert d.nombre == "ANTIOQUIA"

    def test_codigo_padded_to_two_digits(self):
        d = Departamento(codigo="1", nombre="ANTIOQUIA")
        assert d.codigo == "01"


class TestMunicipio:
    def test_basic_fields(self):
        m = Municipio(codigo="280", nombre="TURBO", dpto_codigo="01")
        assert m.codigo == "280"
        assert m.nombre == "TURBO"
        assert m.dpto_codigo == "01"


class TestMesaId:
    def test_folder_name(self):
        mid = MesaId(
            dpto_codigo="01",
            dpto_nombre="ANTIOQUIA",
            municipio_codigo="280",
            municipio_nombre="TURBO",
            zona="03",
            puesto="02",
            mesa="001",
        )
        assert mid.folder_name == "ANTIOQUIA_TURBO_Z03_P02_M001"

    def test_folder_name_normalizes_spaces(self):
        mid = MesaId(
            dpto_codigo="11",
            dpto_nombre="BOGOTA D.C.",
            municipio_codigo="001",
            municipio_nombre="BOGOTA D.C.",
            zona="01",
            puesto="01",
            mesa="001",
        )
        assert " " not in mid.folder_name

    def test_unique_key(self):
        mid = MesaId(
            dpto_codigo="01",
            dpto_nombre="ANTIOQUIA",
            municipio_codigo="280",
            municipio_nombre="TURBO",
            zona="03",
            puesto="02",
            mesa="001",
        )
        assert mid.unique_key == "01-280-03-02-001"


class TestMesa:
    def test_basic_fields(self):
        mid = MesaId(
            dpto_codigo="01",
            dpto_nombre="ANTIOQUIA",
            municipio_codigo="280",
            municipio_nombre="TURBO",
            zona="03",
            puesto="02",
            mesa="001",
        )
        mesa = Mesa(id=mid, url_transmision="https://example.com/acta.pdf")
        assert mesa.id.folder_name == "ANTIOQUIA_TURBO_Z03_P02_M001"
        assert mesa.url_transmision == "https://example.com/acta.pdf"

    def test_url_transmision_optional(self):
        mid = MesaId(
            dpto_codigo="01",
            dpto_nombre="ANTIOQUIA",
            municipio_codigo="280",
            municipio_nombre="TURBO",
            zona="03",
            puesto="02",
            mesa="001",
        )
        mesa = Mesa(id=mid)
        assert mesa.url_transmision is None
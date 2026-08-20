"""Modelos de datos para decretos presidenciales."""
from datetime import date

from pydantic import BaseModel


class Presidente(BaseModel):
    slug: str
    nombre: str
    fecha_inicio: date
    fecha_fin: date | None = None  # None = periodo en curso


class Decreto(BaseModel):
    anio: int
    numero: int
    fecha_firma: date
    titulo: str
    presidente_slug: str | None = None
    url_pdf: str
    path_local: str | None = None

    @property
    def unique_key(self) -> str:
        """Clave natural: la numeración de decretos reinicia cada año en Colombia."""
        return f"{self.anio}-{self.numero}"

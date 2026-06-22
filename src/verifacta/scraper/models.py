import re
from pydantic import BaseModel, field_validator


class Departamento(BaseModel):
    codigo: str
    nombre: str

    @field_validator("codigo")
    @classmethod
    def pad_codigo(cls, v: str) -> str:
        return v.zfill(2)


class Municipio(BaseModel):
    codigo: str
    nombre: str
    dpto_codigo: str


class Zona(BaseModel):
    codigo: str
    nombre: str


class Puesto(BaseModel):
    codigo: str
    nombre: str


class MesaId(BaseModel):
    dpto_codigo: str
    dpto_nombre: str
    municipio_codigo: str
    municipio_nombre: str
    zona: str
    puesto: str
    mesa: str

    @property
    def folder_name(self) -> str:
        dpto = re.sub(r"\s+", "_", self.dpto_nombre.strip())
        mun = re.sub(r"\s+", "_", self.municipio_nombre.strip())
        return f"{dpto}_{mun}_Z{self.zona}_P{self.puesto}_M{self.mesa}"

    @property
    def unique_key(self) -> str:
        return f"{self.dpto_codigo}-{self.municipio_codigo}-{self.zona}-{self.puesto}-{self.mesa}"


class Mesa(BaseModel):
    id: MesaId
    url_transmision: str | None = None
    url_claveros: str | None = None
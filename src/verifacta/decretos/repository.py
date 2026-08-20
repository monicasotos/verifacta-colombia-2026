"""
Persistencia SQLite para metadata de decretos presidenciales.

Tabla `decretos`, clave natural (anio, numero) — la numeración de decretos
reinicia cada año en Colombia. `upsert_many` es idempotente: correr el mismo
mes dos veces actualiza en vez de duplicar.
"""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Session

from .models import Decreto


class Base(DeclarativeBase):
    pass


class DecretoRecord(Base):
    __tablename__ = "decretos"
    __table_args__ = (UniqueConstraint("anio", "numero", name="uq_decreto_anio_numero"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    anio = Column(Integer, nullable=False)
    numero = Column(Integer, nullable=False)
    fecha_firma = Column(Date, nullable=False)
    titulo = Column(String)
    presidente_slug = Column(String)
    url_pdf = Column(String)
    path_local = Column(String)
    fecha_descarga = Column(DateTime)
    creado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DecretosRepository:
    def __init__(self, db_path: Path = Path("results/decretos.db")):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self._engine)

    def upsert_many(self, decretos: list[Decreto]) -> dict:
        """Inserta o actualiza metadata de decretos. Retorna {creados, actualizados}."""
        stats = {"creados": 0, "actualizados": 0}
        with Session(self._engine) as session:
            for d in decretos:
                existing = (
                    session.query(DecretoRecord)
                    .filter_by(anio=d.anio, numero=d.numero)
                    .first()
                )
                if existing:
                    existing.fecha_firma = d.fecha_firma
                    existing.titulo = d.titulo
                    existing.presidente_slug = d.presidente_slug
                    existing.url_pdf = d.url_pdf
                    if d.path_local:
                        existing.path_local = d.path_local
                    stats["actualizados"] += 1
                else:
                    session.add(DecretoRecord(
                        anio=d.anio,
                        numero=d.numero,
                        fecha_firma=d.fecha_firma,
                        titulo=d.titulo,
                        presidente_slug=d.presidente_slug,
                        url_pdf=d.url_pdf,
                        path_local=d.path_local,
                    ))
                    stats["creados"] += 1
            session.commit()
        return stats

    def counts_por_presidente(self) -> dict[str, int]:
        with Session(self._engine) as session:
            rows = (
                session.query(DecretoRecord.presidente_slug, func.count())
                .group_by(DecretoRecord.presidente_slug)
                .all()
            )
        return {(slug or "(sin presidente)"): count for slug, count in rows}

    def all(self) -> list[DecretoRecord]:
        with Session(self._engine) as session:
            session.expire_on_commit = False
            return session.query(DecretoRecord).order_by(DecretoRecord.fecha_firma).all()

    def total(self) -> int:
        with Session(self._engine) as session:
            return session.query(DecretoRecord).count()

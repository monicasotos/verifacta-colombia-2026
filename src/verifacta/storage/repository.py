"""
Persistencia SQLite para resultados de análisis de actas E14.

Tabla principal: `analysis` — un registro por acta analizada con
los votos extraídos, flags de anomalías y metadata de la mesa.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pdf_path = Column(String, unique=True, nullable=False)

    # Identidad de la mesa (extraída del nombre de carpeta)
    dept = Column(String)
    muni_code = Column(String)
    zona = Column(String)
    puesto = Column(String)
    mesa = Column(String)

    # Votos extraídos por LLM
    candidato_1 = Column(Integer)
    candidato_2 = Column(Integer)
    blancos = Column(Integer)
    nulos = Column(Integer)
    no_marcados = Column(Integer)
    suma_total = Column(Integer)

    # anomalías
    consistencia_ok = Column(Boolean)
    tachones = Column(Boolean, default=False)
    tachon_campos = Column(String)       # JSON list
    firmas_faltantes = Column(Boolean, default=False)
    firmas_detalle = Column(String)
    severidad = Column(String)           # "grave" | "moderado" | "leve" | null
    observaciones = Column(Text)
    flagged = Column(Boolean, default=False)

    # Metadata
    modelo = Column(String)
    analizado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _parse_folder(folder_name: str) -> dict:
    """Extrae dept, muni, zona, puesto, mesa del nombre de carpeta."""
    import re
    m = re.match(r"^(.+?)_(.+)_Z(\d+)_P(\d+)_M(\d+)$", folder_name)
    if m:
        return {
            "dept": m.group(1),
            "muni_code": m.group(2),
            "zona": m.group(3),
            "puesto": m.group(4),
            "mesa": m.group(5),
        }
    return {"dept": folder_name, "muni_code": None, "zona": None, "puesto": None, "mesa": None}


class Repository:
    def __init__(self, db_path: Path = Path("results/verifacta.db")):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self._engine)
        self._migrate()

    def _migrate(self) -> None:
        """Añade columnas nuevas a tablas existentes (SQLite no soporta ALTER TABLE DROP COLUMN)."""
        with self._engine.connect() as conn:
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(analysis)"))}
            if "severidad" not in existing:
                conn.execute(text("ALTER TABLE analysis ADD COLUMN severidad TEXT"))
                conn.commit()

    def save_analysis(self, pdf_path: Path, result, modelo: str) -> None:
        """Guarda o actualiza el resultado de análisis de una acta y verifica la escritura."""
        folder_info = _parse_folder(pdf_path.parent.name)
        votos = result.votos or {}

        record = AnalysisRecord(
            pdf_path=str(pdf_path),
            **folder_info,
            candidato_1=votos.get("candidato_1"),
            candidato_2=votos.get("candidato_2"),
            blancos=votos.get("blancos"),
            nulos=votos.get("nulos"),
            no_marcados=votos.get("no_marcados"),
            suma_total=votos.get("suma_total"),
            consistencia_ok=result.consistencia_ok,
            tachones=result.tachones,
            tachon_campos=json.dumps(result.tachon_campos),
            firmas_faltantes=result.firmas_faltantes,
            firmas_detalle=result.firmas_detalle,
            severidad=result.severidad,
            observaciones=result.observaciones,
            flagged=result.flagged,
            modelo=modelo,
        )
        with Session(self._engine) as session:
            existing = session.query(AnalysisRecord).filter_by(pdf_path=str(pdf_path)).first()
            if existing:
                session.delete(existing)
                session.flush()
            session.add(record)
            session.commit()
            self._verify_write(session, str(pdf_path), result)

    def _verify_write(self, session: Session, pdf_path: str, result) -> None:
        """Verifica que el registro guardado coincide con el resultado de Gemini."""
        saved = session.query(AnalysisRecord).filter_by(pdf_path=pdf_path).first()
        if saved is None:
            raise RuntimeError(f"Verificación fallida: registro no encontrado tras guardar ({pdf_path})")

        def bool_eq(a, b):
            return bool(a) == bool(b)

        mismatches = []
        if not bool_eq(saved.flagged, result.flagged):
            mismatches.append(f"flagged: guardado={saved.flagged} esperado={result.flagged}")
        if not bool_eq(saved.tachones, result.tachones):
            mismatches.append(f"tachones: guardado={saved.tachones} esperado={result.tachones}")
        if not bool_eq(saved.firmas_faltantes, result.firmas_faltantes):
            mismatches.append(f"firmas_faltantes: guardado={saved.firmas_faltantes} esperado={result.firmas_faltantes}")
        if saved.consistencia_ok != result.consistencia_ok:
            mismatches.append(f"consistencia_ok: guardado={saved.consistencia_ok} esperado={result.consistencia_ok}")

        if mismatches:
            raise RuntimeError(f"Verificación fallida en {pdf_path}: {'; '.join(mismatches)}")

    def already_analyzed(self, pdf_path: Path) -> bool:
        with Session(self._engine) as session:
            return session.query(AnalysisRecord).filter_by(pdf_path=str(pdf_path)).count() > 0

    def summary(self) -> dict:
        with Session(self._engine) as session:
            total = session.query(AnalysisRecord).count()
            flagged = session.query(AnalysisRecord).filter_by(flagged=True).count()
            inconsistentes = session.query(AnalysisRecord).filter_by(consistencia_ok=False).count()
            tachones = session.query(AnalysisRecord).filter_by(tachones=True).count()
            firmas = session.query(AnalysisRecord).filter_by(firmas_faltantes=True).count()
            graves = session.query(AnalysisRecord).filter_by(severidad="grave").count()
            moderados = session.query(AnalysisRecord).filter_by(severidad="moderado").count()
            leves = session.query(AnalysisRecord).filter_by(severidad="leve").count()
        return {
            "total": total,
            "flagged": flagged,
            "inconsistentes": inconsistentes,
            "tachones": tachones,
            "firmas_faltantes": firmas,
            "graves": graves,
            "moderados": moderados,
            "leves": leves,
        }

    def flagged_records(self, severidad: str | None = None) -> list[AnalysisRecord]:
        with Session(self._engine) as session:
            session.expire_on_commit = False
            q = session.query(AnalysisRecord).filter_by(flagged=True)
            if severidad:
                q = q.filter_by(severidad=severidad)
            return q.order_by(AnalysisRecord.severidad).all()

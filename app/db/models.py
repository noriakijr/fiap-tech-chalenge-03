from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Paciente(Base):
    __tablename__ = "pacientes"

    numero_prontuario: Mapped[str] = mapped_column(String(32), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    data_nascimento: Mapped[date] = mapped_column(Date, nullable=False)

    prontuario: Mapped["Prontuario | None"] = relationship(
        back_populates="paciente",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    exames: Mapped[list["Exame"]] = relationship(
        back_populates="paciente",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    medicamentos: Mapped[list["Medicamento"]] = relationship(
        back_populates="paciente",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Prontuario(Base):
    __tablename__ = "prontuarios"

    numero_prontuario: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("pacientes.numero_prontuario", ondelete="CASCADE"),
        primary_key=True,
    )
    diagnostico_ativo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    alergias: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comorbidades: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    historico_clinico: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    paciente: Mapped[Paciente] = relationship(back_populates="prontuario")


class Exame(Base):
    __tablename__ = "exames"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_prontuario: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("pacientes.numero_prontuario", ondelete="CASCADE"),
        nullable=False,
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    data_solicitacao: Mapped[date] = mapped_column(Date, nullable=False)
    solicitante: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    paciente: Mapped[Paciente] = relationship(back_populates="exames")

    __table_args__ = (
        Index("ix_exames_prontuario_status", "numero_prontuario", "status"),
    )


class Medicamento(Base):
    __tablename__ = "medicamentos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_prontuario: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("pacientes.numero_prontuario", ondelete="CASCADE"),
        nullable=False,
    )
    nome_medicamento: Mapped[str] = mapped_column(String(200), nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    paciente: Mapped[Paciente] = relationship(back_populates="medicamentos")

    __table_args__ = (
        Index("ix_medicamentos_prontuario_ativo", "numero_prontuario", "ativo"),
    )

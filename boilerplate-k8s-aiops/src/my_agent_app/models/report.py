import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from my_agent_app.database import Base


class ReportStatus(StrEnum):
    EM_ANALISE = "EM_ANALISE"
    COMPLETO = "COMPLETO"
    INCOMPLETO = "INCOMPLETO"
    CORRIGINDO = "CORRIGINDO"
    CORRIGIDO = "CORRIGIDO"
    FALHA_CORRECAO = "FALHA_CORRECAO"


_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ReportStatus)


class Report(Base):
    """Relatorio de analise. Status como String + CHECK (e nao ENUM nativo) para evitar ALTER TYPE."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_reports_status"),
        Index("ix_reports_event_uids", "event_uids", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    markdown: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False)
    event_uids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    severity: Mapped[str | None] = mapped_column(Text)
    namespace: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correction_result: Mapped[str | None] = mapped_column(Text)
    correction_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

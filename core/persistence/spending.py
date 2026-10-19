"""Trip groups are independent of financial decisions and imported evidence."""

from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, ForeignKeyConstraint, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.persistence.base import Base, CreatedAt, Identity, Owned
from core.persistence.decisions import LabelFields


class SpendingGroup(Identity, CreatedAt, Owned, LabelFields, Base):
    __tablename__ = "spending_groups"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_spending_groups_owner_id"),
        UniqueConstraint("owner_id", "name", name="uq_spending_groups_name"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 120", name="ck_spending_groups_name"),
        CheckConstraint("version > 0", name="ck_spending_groups_version"),
    )


class SpendingAssignment(Identity, CreatedAt, Owned, Base):
    __tablename__ = "spending_assignments"
    __table_args__ = (
        UniqueConstraint("owner_id", "entry_id", name="uq_spending_assignments_entry"),
        ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_spending_assignments_entry"),
        ForeignKeyConstraint(["owner_id", "group_id"], ["hisaab.spending_groups.owner_id", "hisaab.spending_groups.id"], ondelete="RESTRICT", name="fk_spending_assignments_group"),
        CheckConstraint("version > 0", name="ck_spending_assignments_version"),
    )
    entry_id: Mapped[UUID]
    group_id: Mapped[UUID | None]
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class SpendingEvent(Identity, CreatedAt, Owned, Base):
    __tablename__ = "spending_events"
    __table_args__ = (
        ForeignKeyConstraint(["owner_id", "entry_id"], ["hisaab.entries.owner_id", "hisaab.entries.id"], ondelete="RESTRICT", name="fk_spending_events_entry"),
        UniqueConstraint("owner_id", "entry_id", "version", name="uq_spending_events_version"),
    )
    entry_id: Mapped[UUID]
    version: Mapped[int]
    actor_auth_user_id: Mapped[UUID | None]
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)

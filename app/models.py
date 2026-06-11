# app/models.py
from __future__ import annotations
from typing import Optional

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, Text, ForeignKey


class Base(DeclarativeBase):
    """Base class لكل الموديلات."""
    pass


# ============= المستخدمون / الموظفون =============

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)

    # owner / staff
    role: Mapped[str] = mapped_column(String(20), default="staff")

    # صلاحيات
    can_generate: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=True)
    can_sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_clients: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_settings: Mapped[bool] = mapped_column(Boolean, default=False)

    # تفضيل شخصي لموديلات النص والصورة (مفيد لاحقاً)
    text_model: Mapped[str] = mapped_column(String(80), default="")
    image_model: Mapped[str] = mapped_column(String(80), default="")

    # حدود يومية / رصيد (اختياري للاستخدام لاحقاً)
    daily_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    daily_used: Mapped[int] = mapped_column(Integer, default=0)
    daily_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    credits: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)

    allow_all_clients: Mapped[bool] = mapped_column(Boolean, default=False)


class StaffClient(Base):
    """ربط موظف بعميل معيّن (نستخدمه لاحقاً)."""
    __tablename__ = "staff_clients"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id"), primary_key=True)


# ============= العملاء (سنستخدمه لاحقاً في الخطوة القادمة) =============

class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    overlay_path: Mapped[str] = mapped_column(String(300), default="")
    brand_prompt: Mapped[str] = mapped_column(Text, default="")
    layout_prompt: Mapped[str] = mapped_column(Text, default="")

    design_width: Mapped[int] = mapped_column(Integer, default=1080)
    design_height: Mapped[int] = mapped_column(Integer, default=1080)

    default_text_model: Mapped[str] = mapped_column(String(80), default="")
    default_image_model: Mapped[str] = mapped_column(String(80), default="")


# ============= كتالوج موديلات الذكاء الاصطناعي =============

class ModelCatalog(Base):
    """
    kind:
        - "text"
        - "image"
        - "video"
        - "audio"
    """
    __tablename__ = "model_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # text | image | video | audio
    model_id: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


# ============= الأقسام الديناميكية (شجرة غير محدودة العمق) =============

class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)

    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("sections.id"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parent = relationship("Section", remote_side=[id], backref="children")


# ============= النماذج (Templates) =============

class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)

    section_id: Mapped[int] = mapped_column(Integer, ForeignKey("sections.id"), nullable=False)
    section = relationship("Section", backref="templates")

    base_prompt: Mapped[str] = mapped_column(Text, default="")

    # أمثلة:
    # text_generate / image_generate / image_edit / video_generate / video_edit / audio_generate
    operation: Mapped[str] = mapped_column(String(30))

    model_catalog_id: Mapped[int] = mapped_column(Integer, ForeignKey("model_catalog.id"), nullable=False)
    model: Mapped[ModelCatalog] = relationship("ModelCatalog")

    # none / image_single / image_multi / video_single
    file_requirement: Mapped[str] = mapped_column(String(20), default="none")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
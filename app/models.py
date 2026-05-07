from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("url", name="uq_recipes_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled recipe")
    cuisine: Mapped[str] = mapped_column(String(120), nullable=False, default="unknown")
    prep_time: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    cook_time: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    total_time: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="easy")
    ingredients: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    instructions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    nutrition_estimate: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    substitutions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    shopping_list: Mapped[dict[str, list[str]]] = mapped_column(JSON, nullable=False, default=dict)
    related_recipes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    raw_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scraped_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_llm_output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

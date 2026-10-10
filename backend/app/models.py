from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, unique=True)
    filename: Mapped[str] = mapped_column(Text)
    dirpath: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    codec: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mtime: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    shot_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="discovered", index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proxy_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile: Mapped[str] = mapped_column(String, default="fast")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    delete_marked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    play_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tags: Mapped[list["VideoTag"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Taxonomy(Base):
    __tablename__ = "taxonomy"

    tag: Mapped[str] = mapped_column(String, primary_key=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    video_tags: Mapped[list["VideoTag"]] = relationship(back_populates="taxonomy")


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("videos.id", ondelete="CASCADE")
    )
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    keyframe_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_ja: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VideoTag(Base):
    __tablename__ = "video_tags"
    __table_args__ = (UniqueConstraint("video_id", "tag", name="uq_video_tag"),)

    video_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(
        String, ForeignKey("taxonomy.tag", ondelete="CASCADE"), primary_key=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    frames_hit: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped["Video"] = relationship(back_populates="tags")
    taxonomy: Mapped["Taxonomy"] = relationship(back_populates="video_tags")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("videos.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

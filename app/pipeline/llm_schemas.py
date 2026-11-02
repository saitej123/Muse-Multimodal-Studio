"""Pydantic schemas for LLM slide / publish JSON."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SlideEquation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = ""
    tex: str = ""


class SlideStat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: str = ""
    label: str = ""


class SlideCompare(BaseModel):
    model_config = ConfigDict(extra="ignore")
    left_title: str = "A"
    right_title: str = "B"
    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)


class HubNode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = ""
    sub: str = ""


class SlideHub(BaseModel):
    model_config = ConfigDict(extra="ignore")
    center: str = ""
    subtitle: str = ""
    footer: str = ""
    nodes: list[HubNode] = Field(default_factory=list)


class SlidePanel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = "session"
    subtitle: str = ""
    badge: str = ""
    lines: list[str] = Field(default_factory=list)


class SlideTransform(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_title: str = "SOURCE"
    from_note: str = ""
    to_center: str = ""
    to_nodes: list[str] = Field(default_factory=list)
    footer: str = ""


class FlowStep(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = ""
    sub: str = ""


class SlideFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    orientation: str = "horizontal"
    steps: list[FlowStep] = Field(default_factory=list)


class SlideHook(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: str = ""
    label: str = ""
    punchline: str = ""


class BarsItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = ""
    value: float | int | str = 50
    note: str = ""


class SlideBars(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    items: list[BarsItem] = Field(default_factory=list)


class MatrixItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = ""
    detail: str = ""


class SlideMatrix(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: list[MatrixItem] = Field(default_factory=list)


class SlideDraft(BaseModel):
    """One slide as returned by the LLM (before pipeline coercion)."""

    model_config = ConfigDict(extra="ignore")
    layout: str = "bullets"
    heading: str = ""
    bullets: list[str] = Field(default_factory=list)
    narration: str = ""
    equations: list[SlideEquation | str] = Field(default_factory=list)
    show_flowchart: bool = False
    active_node: str | None = None
    stats: list[SlideStat] = Field(default_factory=list)
    compare: SlideCompare | None = None
    steps: list[str] = Field(default_factory=list)
    quote: str = ""
    hub: SlideHub | None = None
    panel: SlidePanel | None = None
    transform: SlideTransform | None = None
    flow: SlideFlow | None = None
    hook: SlideHook | None = None
    bars: SlideBars | None = None
    matrix: SlideMatrix | None = None
    image: str | None = None
    image_caption: str = ""

    @field_validator("bullets", "steps", mode="before")
    @classmethod
    def _str_list(cls, v: Any) -> list:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        return []


class SlideDeckLLM(BaseModel):
    """Top-level slides JSON from the LLM."""

    model_config = ConfigDict(extra="ignore")
    title: str = "Overview"
    flowchart: str = ""
    slides: list[SlideDraft] = Field(default_factory=list, min_length=1)

    @field_validator("slides", mode="before")
    @classmethod
    def _need_slides(cls, v: Any) -> list:
        if not isinstance(v, list):
            return []
        return v


class PublishMetaLLM(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(t).strip() for t in v if str(t).strip()]


class SocialPostLLM(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)

    @field_validator("hashtags", mode="before")
    @classmethod
    def _tags(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(t).strip() for t in v if str(t).strip()]

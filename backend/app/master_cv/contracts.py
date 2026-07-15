from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortraitCrop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stays_inside_image(self) -> "PortraitCrop":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("crop must remain within normalized image bounds")
        return self


class FocalPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)


class PortraitAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    mime_type: str
    width: int
    height: int
    crop: PortraitCrop
    focal_point: FocalPoint
    status: str


class PhotoDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    shape: Literal["circle", "rounded", "square"] = "rounded"
    position: Literal["header_left", "header_right", "sidebar"] = "header_right"
    inclusion_policy: Literal["always", "german_swiss", "never"] = "german_swiss"


class MasterCvDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1)
    template_version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+$")
    page_size: Literal["A4"] = "A4"
    page_count: Literal[1, 2] = 1
    density: Literal["airy", "balanced", "compact"] = "balanced"
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    font_family: str | None = Field(default=None, max_length=100)
    photo: PhotoDesign = Field(default_factory=PhotoDesign)


class MasterCvBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str = Field(min_length=1)
    kind: Literal["heading", "paragraph", "entry", "bullet", "skill", "contact"]
    text: str = Field(max_length=5000)
    claim_refs: list[str] = Field(default_factory=list)
    profile_field_refs: list[str] = Field(default_factory=list)
    visible: bool = True
    metadata: dict[str, Any] | None = None


class MasterCvSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(min_length=1)
    type: Literal[
        "header", "summary", "experience", "projects", "education", "skills", "languages",
        "certifications", "achievements", "custom"
    ]
    title: str = Field(max_length=100)
    blocks: list[MasterCvBlock] = Field(default_factory=list)


class MasterCvDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    document_snapshot_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    user_profile_id: str | None = None
    created_at: datetime
    title: str = Field(min_length=1, max_length=200)
    locale: str = Field(default="en", min_length=2, max_length=35)
    market: str = Field(default="international", min_length=2, max_length=35)
    page_goal: Literal[1, 2] = 1
    portrait_asset_id: str | None = None
    portrait_variant_id: str | None = None
    lifecycle_status: Literal["candidate", "needs_review", "approved", "superseded", "rejected"] = "candidate"
    review_flags: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    design: MasterCvDesign
    sections: list[MasterCvSection]


class BlockPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=5000)
    visible: bool | None = None
    claim_refs: list[str] | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class ClaimProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)
    category: Literal["experience", "project", "education", "skill", "language", "certification", "achievement", "other"]
    statement: str = Field(min_length=1)
    source_refs: list[str]
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1)
    related_claim_refs: list[str] = Field(default_factory=list)
    needs_review: Literal[True] = True


class MasterCvClaimProposals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    profile_id: str = Field(min_length=1)
    proposals: list[ClaimProposal] = Field(default_factory=list)


class BuilderChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=12000)


class BuilderSessionResponse(BaseModel):
    session_id: str
    run_id: str
    status: str
    candidate: MasterCvDocument | None = None
    transcript: list[dict[str, Any]] = Field(default_factory=list)


class MasterCvVersionResponse(BaseModel):
    document_snapshot_id: str
    version_number: int
    title: str
    template_id: str
    locale: str
    page_count: int
    status: str
    portrait_asset_id: str | None = None
    created_at: datetime
    approved_at: datetime | None = None

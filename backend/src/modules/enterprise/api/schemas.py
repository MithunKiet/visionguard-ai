from pydantic import BaseModel, Field


class UpdateBrandingRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    tagline: str | None = Field(None, max_length=300)
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_url: str | None = Field(None, max_length=500)
    favicon_url: str | None = Field(None, max_length=500)

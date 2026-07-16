from pydantic import BaseModel, EmailStr, Field


class UpdateBrandingRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    tagline: str | None = Field(None, max_length=300)
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_url: str | None = Field(None, max_length=500)
    favicon_url: str | None = Field(None, max_length=500)


class CreateEnterpriseRequest(BaseModel):
    """Platform-level onboarding: creates the enterprise and its first
    ENTERPRISE_ADMIN user together — an enterprise with no admin would be
    inaccessible, so these are never created separately."""
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    industry: str | None = Field(None, max_length=100)
    contact_person: str | None = Field(None, max_length=200)
    contact_email: EmailStr | None = None
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    admin_name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr

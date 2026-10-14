"""Pydantic data models for Minnesota Park & Campsite Explorer."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Campsite(BaseModel):
    """Represents a single campsite or lodging unit from the Minnesota Park Google Sheet."""

    id: str
    park: str
    park_type: str = ""
    campground: str = ""
    site_name: str = ""
    unit_type: str = ""
    site_type: str = ""
    lat: float
    lon: float
    county: str = ""
    tourism_region: str = ""
    electric_30amp: bool = False
    electric_50amp: bool = False
    pad_length_ft: Optional[int] = None
    pad_width_ft: Optional[int] = None
    pad_surface: str = ""
    pull_through: bool = False
    tent_pad: str = ""
    feet_to_restroom: Optional[int] = None
    feet_to_shower: Optional[int] = None
    feet_to_water: Optional[int] = None
    feet_to_dump_station: Optional[int] = None
    waterfront: bool = False
    pets_allowed: bool = False
    max_people: Optional[int] = None
    max_vehicles: Optional[int] = None
    fire_ring: bool = False
    picnic_table: bool = False
    food_locker: bool = False
    shade: str = ""
    ada_accessible: bool = False


class ParkSummary(BaseModel):
    """Aggregated summary of a Minnesota Park and its campsites."""

    park: str
    park_type: str
    county: str
    tourism_region: str
    lat: float
    lon: float
    total_sites: int
    campgrounds: List[str] = Field(default_factory=list)
    unit_types: List[str] = Field(default_factory=list)
    site_types: List[str] = Field(default_factory=list)
    has_electric: bool = False
    has_waterfront: bool = False
    has_ada: bool = False
    max_pad_length_ft: Optional[int] = None


class FilterFacets(BaseModel):
    """Available distinct values for UI filter controls."""

    parks: List[str]
    park_types: List[str]
    tourism_regions: List[str]
    counties: List[str]
    unit_types: List[str]
    site_types: List[str]
    shade_options: List[str]
    pad_surfaces: List[str]
    max_pad_length: int
    max_people_limit: int


class DatasetMetadata(BaseModel):
    """Metadata describing the currently loaded Google Sheet dataset."""

    sheet_id: str
    sheet_gid: str
    sheet_url: str
    source: str
    last_synced_at: str
    total_campsites: int
    total_parks: int
    total_counties: int
    facets: FilterFacets


class UserProfile(BaseModel):
    """Authenticated user profile from federated Google IdP."""

    sub: str
    email: str
    name: str
    picture: str = ""
    provider: str = "google"


class UserNotePayload(BaseModel):
    """Payload for saving a personal campsite note or rating."""

    note: str = Field(default="", max_length=2000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)


class GoogleTokenPayload(BaseModel):
    """Payload containing a Google Identity Services credential (ID token)."""

    credential: str

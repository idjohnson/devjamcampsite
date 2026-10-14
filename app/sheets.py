"""Google Sheets data fetcher, parser, and in-memory query engine for Minnesota Park Campsites."""

import csv
import hashlib
import io
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from app.config import settings
from app.models import Campsite, DatasetMetadata, FilterFacets, ParkSummary

logger = logging.getLogger(__name__)

FALLBACK_CSV_PATH = Path(__file__).resolve().parent / "data" / "mn_campsites_fallback.csv"


def _parse_bool(val: Optional[str]) -> bool:
    if not val:
        return False
    return val.strip().lower() in ("yes", "true", "1", "y")


def _parse_int(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class GoogleSheetsCampsiteService:
    """Fetches, caches, and indexes Minnesota Park campsite data from Google Sheets."""

    def __init__(self) -> None:
        self._campsites: List[Campsite] = []
        self._campsites_by_id: Dict[str, Campsite] = {}
        self._parks: List[ParkSummary] = []
        self._facets: Optional[FilterFacets] = None
        self._last_synced_epoch: float = 0.0
        self._last_synced_iso: str = "Never"
        self._source: str = "uninitialized"

    async def ensure_loaded(self, force_refresh: bool = False) -> None:
        """Ensure campsite data is loaded and within cache TTL."""
        now = time.time()
        is_expired = (now - self._last_synced_epoch) > settings.sheet_cache_ttl_seconds
        if not self._campsites or force_refresh or is_expired:
            await self.refresh_data()

    async def refresh_data(self) -> DatasetMetadata:
        """Fetch latest data from Google Sheets (with API v4, CSV export, and local fallback)."""
        csv_text: Optional[str] = None
        source = "google_sheets_csv_export"

        # 1. If GOOGLE_SHEETS_API_KEY is configured, try Google Sheets API v4 first
        if settings.google_sheets_api_key.strip():
            try:
                csv_text = await self._fetch_via_sheets_api_v4()
                source = "google_sheets_api_v4"
            except Exception as exc:
                logger.warning("Google Sheets API v4 fetch failed (%s), falling back to CSV export.", exc)

        # 2. Fetch directly from the Google Sheets CSV export endpoint
        if not csv_text:
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                    response = await client.get(settings.sheet_csv_export_url)
                    response.raise_for_status()
                    text = response.text
                    if "park,park_type" in text[:200]:
                        csv_text = text
                        source = "google_sheets_live_csv"
                    else:
                        logger.warning("Unexpected content from Google Sheets export URL; using fallback CSV.")
            except Exception as exc:
                logger.warning("Live Google Sheets fetch failed (%s); falling back to bundled snapshot.", exc)

        # 3. Fallback to bundled snapshot CSV if offline or unreachable
        if not csv_text:
            if FALLBACK_CSV_PATH.exists():
                csv_text = FALLBACK_CSV_PATH.read_text(encoding="utf-8")
                source = "bundled_google_sheet_snapshot"
            else:
                raise RuntimeError("Unable to load Minnesota campsite data from Google Sheets or local fallback.")

        self._parse_and_index(csv_text, source)
        return self.get_metadata()

    async def _fetch_via_sheets_api_v4(self) -> str:
        """Fetch sheet values via Google Sheets API v4 and convert to CSV text."""
        api_key = settings.google_sheets_api_key.strip()
        meta_url = f"https://sheets.googleapis.com/v4/spreadsheets/{settings.google_sheet_id}?key={api_key}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            meta_resp = await client.get(meta_url)
            meta_resp.raise_for_status()
            meta_json = meta_resp.json()

            sheet_title = None
            for sheet in meta_json.get("sheets", []):
                props = sheet.get("properties", {})
                if str(props.get("sheetId")) == str(settings.google_sheet_gid):
                    sheet_title = props.get("title")
                    break
            if not sheet_title and meta_json.get("sheets"):
                sheet_title = meta_json["sheets"][0]["properties"]["title"]

            values_url = (
                f"https://sheets.googleapis.com/v4/spreadsheets/{settings.google_sheet_id}"
                f"/values/{sheet_title}!A1:AD10000?key={api_key}"
            )
            val_resp = await client.get(values_url)
            val_resp.raise_for_status()
            rows = val_resp.json().get("values", [])
            if not rows:
                raise ValueError("Empty values returned from Google Sheets API v4")

            output = io.StringIO()
            writer = csv.writer(output)
            headers = rows[0]
            writer.writerow(headers)
            for row in rows[1:]:
                padded = row + [""] * max(0, len(headers) - len(row))
                writer.writerow(padded[: len(headers)])
            return output.getvalue()

    def _parse_and_index(self, csv_text: str, source: str) -> None:
        """Parse CSV rows into Campsite models, build park aggregations and filter facets."""
        reader = csv.DictReader(io.StringIO(csv_text))
        campsites: List[Campsite] = []
        by_id: Dict[str, Campsite] = {}
        seen_ids: Dict[str, int] = {}

        parks_set = set()
        park_types_set = set()
        regions_set = set()
        counties_set = set()
        unit_types_set = set()
        site_types_set = set()
        shade_set = set()
        surfaces_set = set()
        max_pad = 0
        max_people = 0

        park_groups: Dict[str, List[Campsite]] = {}

        for row in reader:
            try:
                lat = float(row.get("lat", "") or 0)
                lon = float(row.get("lon", "") or 0)
            except (ValueError, TypeError):
                continue
            if lat == 0 or lon == 0:
                continue

            park = (row.get("park") or "").strip()
            park_type = (row.get("park_type") or "").strip()
            campground = (row.get("campground") or "Main Area").strip() or "Main Area"
            site_name = (row.get("site_name") or "").strip()
            unit_type = (row.get("unit_type") or "Campsite").strip() or "Campsite"
            site_type = (row.get("site_type") or "Standard").strip() or "Standard"
            county = (row.get("county") or "").strip()
            tourism_region = (row.get("tourism_region") or "").strip()
            shade = (row.get("shade") or "").strip()
            pad_surface = (row.get("pad_surface") or "").strip()

            base_key = f"{park}|{campground}|{site_name}|{unit_type}|{lat:.5f}|{lon:.5f}"
            short_hash = hashlib.sha1(base_key.encode("utf-8")).hexdigest()[:10]
            site_id = f"{_slugify(park)[:24]}-{_slugify(site_name or unit_type)[:12]}-{short_hash}"
            if site_id in seen_ids:
                seen_ids[site_id] += 1
                site_id = f"{site_id}-{seen_ids[site_id]}"
            else:
                seen_ids[site_id] = 1

            pad_len = _parse_int(row.get("pad_length_ft"))
            people_lim = _parse_int(row.get("max_people"))

            site = Campsite(
                id=site_id,
                park=park,
                park_type=park_type,
                campground=campground,
                site_name=site_name,
                unit_type=unit_type,
                site_type=site_type,
                lat=lat,
                lon=lon,
                county=county,
                tourism_region=tourism_region,
                electric_30amp=_parse_bool(row.get("electric_30amp")),
                electric_50amp=_parse_bool(row.get("electric_50amp")),
                pad_length_ft=pad_len,
                pad_width_ft=_parse_int(row.get("pad_width_ft")),
                pad_surface=pad_surface,
                pull_through=_parse_bool(row.get("pull_through")),
                tent_pad=(row.get("tent_pad") or "").strip(),
                feet_to_restroom=_parse_int(row.get("feet_to_restroom")),
                feet_to_shower=_parse_int(row.get("feet_to_shower")),
                feet_to_water=_parse_int(row.get("feet_to_water")),
                feet_to_dump_station=_parse_int(row.get("feet_to_dump_station")),
                waterfront=_parse_bool(row.get("waterfront")),
                pets_allowed=_parse_bool(row.get("pets_allowed")),
                max_people=people_lim,
                max_vehicles=_parse_int(row.get("max_vehicles")),
                fire_ring=_parse_bool(row.get("fire_ring")),
                picnic_table=_parse_bool(row.get("picnic_table")),
                food_locker=_parse_bool(row.get("food_locker")),
                shade=shade,
                ada_accessible=_parse_bool(row.get("ada_accessible")),
            )

            campsites.append(site)
            by_id[site.id] = site
            park_groups.setdefault(park, []).append(site)

            if park:
                parks_set.add(park)
            if park_type:
                park_types_set.add(park_type)
            if tourism_region:
                regions_set.add(tourism_region)
            if county:
                counties_set.add(county)
            if unit_type:
                unit_types_set.add(unit_type)
            if site_type:
                site_types_set.add(site_type)
            if shade:
                shade_set.add(shade)
            if pad_surface and pad_surface.lower() != "none":
                surfaces_set.add(pad_surface)
            if pad_len and pad_len > max_pad:
                max_pad = pad_len
            if people_lim and people_lim > max_people:
                max_people = people_lim

        # Build ParkSummary list
        park_summaries: List[ParkSummary] = []
        for park_name in sorted(park_groups.keys()):
            p_sites = park_groups[park_name]
            avg_lat = sum(s.lat for s in p_sites) / len(p_sites)
            avg_lon = sum(s.lon for s in p_sites) / len(p_sites)
            pad_lengths = [s.pad_length_ft for s in p_sites if s.pad_length_ft is not None]
            park_summaries.append(
                ParkSummary(
                    park=park_name,
                    park_type=p_sites[0].park_type,
                    county=p_sites[0].county,
                    tourism_region=p_sites[0].tourism_region,
                    lat=round(avg_lat, 6),
                    lon=round(avg_lon, 6),
                    total_sites=len(p_sites),
                    campgrounds=sorted({s.campground for s in p_sites if s.campground}),
                    unit_types=sorted({s.unit_type for s in p_sites if s.unit_type}),
                    site_types=sorted({s.site_type for s in p_sites if s.site_type}),
                    has_electric=any(s.electric_30amp or s.electric_50amp for s in p_sites),
                    has_waterfront=any(s.waterfront for s in p_sites),
                    has_ada=any(s.ada_accessible for s in p_sites),
                    max_pad_length_ft=max(pad_lengths) if pad_lengths else None,
                )
            )

        self._campsites = campsites
        self._campsites_by_id = by_id
        self._parks = park_summaries
        self._facets = FilterFacets(
            parks=sorted(parks_set),
            park_types=sorted(park_types_set),
            tourism_regions=sorted(regions_set),
            counties=sorted(counties_set),
            unit_types=sorted(unit_types_set),
            site_types=sorted(site_types_set),
            shade_options=sorted(shade_set),
            pad_surfaces=sorted(surfaces_set),
            max_pad_length=max_pad or 120,
            max_people_limit=max_people or 200,
        )
        self._last_synced_epoch = time.time()
        self._last_synced_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._source = source
        logger.info(
            "Loaded %d campsites across %d Minnesota parks (source=%s)",
            len(campsites),
            len(park_summaries),
            source,
        )

    def get_metadata(self) -> DatasetMetadata:
        if not self._facets:
            raise RuntimeError("Dataset not loaded yet")
        return DatasetMetadata(
            sheet_id=settings.google_sheet_id,
            sheet_gid=settings.google_sheet_gid,
            sheet_url=settings.sheet_edit_url,
            source=self._source,
            last_synced_at=self._last_synced_iso,
            total_campsites=len(self._campsites),
            total_parks=len(self._parks),
            total_counties=len(self._facets.counties),
            facets=self._facets,
        )

    def get_parks(self) -> List[ParkSummary]:
        return self._parks

    def get_campsite_by_id(self, campsite_id: str) -> Optional[Campsite]:
        return self._campsites_by_id.get(campsite_id)

    def filter_campsites(
        self,
        q: Optional[str] = None,
        park: Optional[str] = None,
        park_type: Optional[str] = None,
        tourism_region: Optional[str] = None,
        county: Optional[str] = None,
        unit_type: Optional[str] = None,
        site_type: Optional[str] = None,
        shade: Optional[str] = None,
        electric: Optional[bool] = None,
        electric_50amp: Optional[bool] = None,
        waterfront: Optional[bool] = None,
        ada_accessible: Optional[bool] = None,
        pets_allowed: Optional[bool] = None,
        food_locker: Optional[bool] = None,
        min_pad_length: Optional[int] = None,
        min_people: Optional[int] = None,
        favorite_ids: Optional[set[str]] = None,
    ) -> List[Campsite]:
        """Filter in-memory campsites using multi-faceted criteria."""
        results = self._campsites

        if favorite_ids is not None:
            results = [s for s in results if s.id in favorite_ids]

        if park:
            results = [s for s in results if s.park == park]

        if park_type:
            results = [s for s in results if s.park_type == park_type]

        if tourism_region:
            results = [s for s in results if s.tourism_region == tourism_region]

        if county:
            results = [s for s in results if s.county == county]

        if unit_type:
            results = [s for s in results if s.unit_type == unit_type]

        if site_type:
            results = [s for s in results if s.site_type == site_type]

        if shade:
            results = [s for s in results if s.shade == shade]

        if electric is True:
            results = [s for s in results if s.electric_30amp or s.electric_50amp]

        if electric_50amp is True:
            results = [s for s in results if s.electric_50amp]

        if waterfront is True:
            results = [s for s in results if s.waterfront]

        if ada_accessible is True:
            results = [s for s in results if s.ada_accessible]

        if pets_allowed is True:
            results = [s for s in results if s.pets_allowed]

        if food_locker is True:
            results = [s for s in results if s.food_locker]

        if min_pad_length is not None and min_pad_length > 0:
            results = [
                s for s in results if s.pad_length_ft is not None and s.pad_length_ft >= min_pad_length
            ]

        if min_people is not None and min_people > 0:
            results = [
                s for s in results if s.max_people is not None and s.max_people >= min_people
            ]

        if q and q.strip():
            query = q.strip().lower()
            results = [
                s
                for s in results
                if query in s.park.lower()
                or query in s.campground.lower()
                or query in s.site_name.lower()
                or query in s.county.lower()
                or query in s.site_type.lower()
                or query in s.unit_type.lower()
            ]

        return results


sheets_service = GoogleSheetsCampsiteService()

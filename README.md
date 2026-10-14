# Minnesota Park & Campsite Explorer

A Python **FastAPI** web application that leverages the **Minnesota Park Information Google Sheet** (`1CW-0euFLFz24nzcXNrTY24IoqTX9BCHLX5fdLjxAHgk`, `gid=459530859`) to display **5,584 campsites across 109 Minnesota State Parks, State Forests, State Recreation Areas, and State Water Trails** on an interactive **Google Map** with **Federated Google IdP (OAuth 2.0 / OIDC)** login.

## Key Features

- **Live Google Sheets Integration:** Automatically fetches, normalizes, and caches all 5,584 campsites and 30 site attributes from the Minnesota Park Information Google Sheet (via Google Sheets API v4, live CSV export, and a bundled offline fallback snapshot).
- **Interactive Google Maps & Marker Clustering:** Plots all 5,584 campsites with color-coded pins by site/unit type, MarkerClusterer support, a **Parks Overview (109 Parks)** mode, and an automatic interactive OpenStreetMap/USGS Topo/Satellite fallback when `GOOGLE_MAPS_API_KEY` is not yet configured.
- **Multi-Faceted Campsite Filtering:** Filter by search query, Tourism Region (`Northeast`, `Northwest`, `Central`, `Metro`, `Southern`), Park System Type, Specific Park, County, Unit Type (`Campsite`, `Tipi`, `Wall Tent`, `Group Camp`), Site Access Type (`Backpack`, `Canoe-In/Boat-In`, `Cart-In`, `Drive-In Electric`, `Walk-In`, etc.), Shade, 30A/50A Electric, Waterfront, ADA Accessibility, Pets Allowed, Bear Food Locker, Minimum RV Pad Length, and Party Size.
- **Federated Google IdP Authentication:** Supports Google OAuth 2.0 / OIDC redirect login and Google Identity Services (Sign In With Google) JWT verification, unlocking saved favorite campsites, personal site notes & star ratings, and on-demand Google Sheet sync.
- **Docker & Docker Compose Ready:** Includes a production-ready `Dockerfile`, `docker-compose.yml`, container healthcheck, and persistent SQLite volume.

## Documentation

- **[SETUP.md](SETUP.md)** — Step-by-step setup guide for Google Cloud Console, Google Maps JavaScript API, Federated Google IdP (OAuth 2.0 / OIDC), Google Sheets configuration, and `.env` variables.
- **[INSTALL.md](INSTALL.md)** — Installation, Docker Compose execution, local virtual environment setup, testing, and troubleshooting instructions.

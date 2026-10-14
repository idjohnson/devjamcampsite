# Installation & Deployment Guide (`INSTALL.md`)

This guide covers installing, running, testing, and managing the **Minnesota Park & Campsite Explorer** using **Docker & Docker Compose** (recommended) or a local Python virtual environment.

---

## Prerequisites

- **Docker Engine** (v20.10+) and **Docker Compose** (v2.0+ plugin `docker compose`)
- *(Optional for non-Docker local development)* **Python 3.11+** and `pip`
- Configured `.env` file (see [SETUP.md](SETUP.md) for Google Maps and Google IdP configuration)

---

## Option 1: Run with Docker & Docker Compose (Recommended)

### Step 1: Prepare the Environment File
From the project root directory (`/home/builder/Workspaces/mncampsiteapp`):

```bash
cp .env.example .env
```

Edit `.env` if you have your `GOOGLE_MAPS_API_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` ready (or leave the defaults to start immediately with the built-in interactive map fallback and demo IdP login).

### Step 2: Build and Start the Container
Run Docker Compose in detached mode:

```bash
docker compose up -d --build
```

### Step 3: Verify the Application is Running
Check container status and health:

```bash
docker compose ps
curl http://localhost:8000/api/health
```

Expected health check response:
```json
{
  "status": "healthy",
  "app": "Minnesota Park & Campsite Explorer",
  "sheet_source": "google_sheets_live_csv",
  "last_synced_at": "2026-10-14 22:45:00 UTC",
  "total_campsites": 5584,
  "total_parks": 109
}
```

### Step 4: Access the Web Interface & API Docs
- **Interactive Web Application:** [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI / Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Reference:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Managing the Docker Compose Stack

- **View real-time application logs:**
  ```bash
  docker compose logs -f mncampsiteapp
  ```
- **Restart after editing `.env`:**
  ```bash
  docker compose up -d
  ```
- **Stop the containers (preserving saved favorites & notes in Docker volume `mn_campsite_data`):**
  ```bash
  docker compose down
  ```
- **Stop and remove persistent data volume:**
  ```bash
  docker compose down -v
  ```

---

## Option 2: Local Python Installation (Without Docker)

If you want to run or develop the FastAPI app directly on the host machine:

### Step 1: Create and Activate a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Start the FastAPI Server with Uvicorn
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Running Automated Tests

You can run the test suite either inside the Docker container or locally with `pytest`:

```bash
# Inside the running Docker container:
docker compose exec mncampsiteapp pytest -v

# Or locally:
pytest -v
```

---

## Troubleshooting

1. **Port `8000` is already in use:**
   Change `APP_PORT=8080` in your `.env` file and run `docker compose up -d`. The app will be available at `http://localhost:8080`.
2. **`redirect_uri_mismatch` error during Google Sign-In:**
   Ensure `GOOGLE_REDIRECT_URI` in `.env` exactly matches the URI configured under **Authorized redirect URIs** in Google Cloud Console (default: `http://localhost:8000/auth/callback`).
3. **Google Maps shows "For development purposes only" or switches to the fallback map:**
   Ensure the **Maps JavaScript API** is enabled in your Google Cloud project and billing is linked, or use the **Map Settings** button in the top navigation bar to update or clear your browser test key.

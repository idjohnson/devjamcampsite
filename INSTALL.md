# Installation & Deployment Guide (`INSTALL.md`)

This guide covers building, installing, and deploying the **Minnesota Park & Campsite Explorer** using:
1. **Kubernetes & Helm** (exposing `https://camping.tpk.pw` via Ingress)
2. **Docker & Docker Compose**
3. **Local Python Virtual Environment**

---

## Option 1: Kubernetes & Helm Deployment (`https://camping.tpk.pw`)

The Helm chart is located in [`helm/mncampsiteapp/`](helm/mncampsiteapp/) and includes:
- `Deployment` ([`deployment.yaml`](helm/mncampsiteapp/templates/deployment.yaml)) with `/api/health` liveness/readiness probes and automatic rolling restarts on ConfigMap/Secret changes
- `Service` ([`service.yaml`](helm/mncampsiteapp/templates/service.yaml)) exposing port `80` -> container port `8000`
- `Ingress` ([`ingress.yaml`](helm/mncampsiteapp/templates/ingress.yaml)) pre-configured for `https://camping.tpk.pw` with `nginx` IngressClass and TLS (`camping-tpk-pw-tls`)
- `Secret` ([`secret.yaml`](helm/mncampsiteapp/templates/secret.yaml)) & `ConfigMap` ([`configmap.yaml`](helm/mncampsiteapp/templates/configmap.yaml)) for all `.env` variables
- `PersistentVolumeClaim` ([`pvc.yaml`](helm/mncampsiteapp/templates/pvc.yaml)) mounted at `/app/data` for SQLite persistence

### Step 1: Build and Push the Docker Image to Your Container Registry
```bash
export REGISTRY_IMAGE="ghcr.io/your-org/mncampsiteapp"
export IMAGE_TAG="1.0.0"

docker build -t "${REGISTRY_IMAGE}:${IMAGE_TAG}" -t "${REGISTRY_IMAGE}:latest" .
docker push "${REGISTRY_IMAGE}:${IMAGE_TAG}"
docker push "${REGISTRY_IMAGE}:latest"
```

### Step 2: Deploy with Helm Passing Secrets via `--set`
```bash
helm upgrade --install mncampsiteapp ./helm/mncampsiteapp \
  --namespace camping --create-namespace \
  --set image.repository="ghcr.io/your-org/mncampsiteapp" \
  --set image.tag="1.0.0" \
  --set secrets.SESSION_SECRET_KEY="$(openssl rand -hex 32)" \
  --set secrets.GOOGLE_MAPS_API_KEY="AIzaSyYourGoogleMapsKey" \
  --set secrets.GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com" \
  --set secrets.GOOGLE_CLIENT_SECRET="GOCSPX-your-client-secret" \
  --set secrets.GOOGLE_SHEETS_API_KEY="" \
  --set config.ENABLE_DEMO_AUTH="false"
```

### Alternative: Deploy Using a Custom `my-values.yaml` File
If you prefer keeping your secrets in a local git-ignored file (`my-values.yaml`):

```yaml
image:
  repository: ghcr.io/your-org/mncampsiteapp
  tag: "1.0.0"

config:
  GOOGLE_REDIRECT_URI: "https://camping.tpk.pw/auth/callback"
  ENABLE_DEMO_AUTH: "false"

secrets:
  SESSION_SECRET_KEY: "your-production-random-secret-key"
  GOOGLE_MAPS_API_KEY: "AIzaSyYourGoogleMapsKey"
  GOOGLE_CLIENT_ID: "your-client-id.apps.googleusercontent.com"
  GOOGLE_CLIENT_SECRET: "GOCSPX-your-client-secret"
  GOOGLE_SHEETS_API_KEY: ""
```

Then deploy with:
```bash
helm upgrade --install mncampsiteapp ./helm/mncampsiteapp \
  --namespace camping --create-namespace \
  -f my-values.yaml
```

### Step 3: Verify the Kubernetes Deployment
```bash
kubectl -n camping get pods,svc,ingress,pvc
curl https://camping.tpk.pw/api/health
```

---

## Option 2: Run with Docker & Docker Compose

### Step 1: Prepare the Environment File
```bash
cp .env.example .env
```

### Step 2: Build and Start the Container
```bash
docker compose up -d --build
```

### Step 3: Verify the Application is Running
```bash
docker compose ps
curl http://localhost:8000/api/health
```

- **Interactive Web Application:** [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI / Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Option 3: Local Python Installation (Without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Running Automated Tests

```bash
# Inside the running Docker container:
docker compose exec mncampsiteapp pytest -v

# Or locally:
.venv/bin/pytest -v
```

# ENVIRONMENT.md — CritiqAI

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Credential Setup](#credential-setup)
3. [Credential Waterfall](#credential-waterfall)
4. [MCP Server Setup](#mcp-server-setup)
5. [Environment Variables](#environment-variables)
6. [Installation](#installation)
7. [GCP Deployment](#gcp-deployment)
8. [Verification](#verification)
9. [Common Issues](#common-issues)

---

## System Requirements

| Requirement | Minimum |
| --- | --- |
| Python | 3.11 or higher |
| Operating System | Linux or macOS (Windows is **not tested**) |
| Disk Space | 500 MB free |
| Network | Internet connection required (Google AI Studio API) |

---

## Credential Setup

CritiqAI uses **Google AI Studio (free tier)** as its AI engine. No billing account, no Vertex AI, no gcloud CLI required.

### Get a Google AI Studio API Key

1. Go to [https://aistudio.google.com](https://aistudio.google.com)
2. Sign in with your Google account
3. Click **Get API key** in the left sidebar
4. Click **Create API key** and copy the generated key

### Configure your `.env` file

```dotenv
GOOGLE_API_KEY=AIza...your_key_here...
```

**Model in use:** `gemini-2.5-flash-lite` (primary; automatic fallback chain: `gemini-2.0-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash`)

> No billing required. Free tier supports ~317 debate sessions per day at the current token budget.

---

## Credential Waterfall

CritiqAI resolves the AI credential at startup in this order:

```text
┌─────────────────────────────────────────────┐
│  1. GOOGLE_API_KEY in .env / environment    │
└────────────────────┬────────────────────────┘
                     │ not set
                     ▼
┌─────────────────────────────────────────────┐
│  2. Structured Error — Halt                 │
│     (no silent fallback, no Ollama)         │
└─────────────────────────────────────────────┘
```

**Example error when no credential is found:**

```text
[CritiqAI] FATAL: No AI credential resolved.

  Checked in order:
    [✗] GOOGLE_API_KEY — not set in .env or environment

  Action required:
    Set GOOGLE_API_KEY in your .env file.
    Get a free key at: https://aistudio.google.com

  See ENVIRONMENT.md — Credential Setup for instructions.
```

---

## MCP Server Setup

CritiqAI connects to four MCP servers. Complete the setup for each one.

---

### 1. Google Drive MCP (read-only)

**Purpose:** Read student submission files from a designated Drive folder.

**OAuth scope required:** `https://www.googleapis.com/auth/drive.readonly`

**Setup steps:**

1. In [Google Cloud Console](https://console.cloud.google.com), navigate to **APIs & Services → OAuth consent screen**
2. Configure the consent screen (External or Internal user type)
3. Add the scope `drive.readonly` under **Scopes**
4. Download the OAuth 2.0 client credentials JSON and note your `client_id` and `client_secret`
5. Set in `.env`:
   ```dotenv
   GOOGLE_OAUTH_CLIENT_ID=your_client_id
   GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
   DRIVE_MCP_URL=http://localhost:3000/mcp/sse
   ```

The Drive MCP server runs on port 3000 by default.

---

### 2. Google Sheets MCP (append + read)

**Purpose:** Log debate session history and scores per student.

**OAuth scope required:** `https://www.googleapis.com/auth/spreadsheets`

**Setup steps:**

1. In Google Cloud Console, add the `spreadsheets` scope to the same OAuth consent screen
2. Create a blank Google Sheet and copy its ID from the URL:
   `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`
3. Set in `.env`:
   ```dotenv
   DEBATE_LOG_SHEET_ID=1xYz...your_sheet_id...
   DEBATE_LOG_RANGE=Sheet1!A:G
   SHEETS_MCP_URL=http://localhost:3001/mcp/sse
   ```

---

### 3. Gmail MCP (compose only)

**Purpose:** Draft grading reports for teacher review before sending.

**OAuth scope required:** `https://www.googleapis.com/auth/gmail.compose`

> **Important:** Only the `gmail.compose` scope is needed. Do **NOT** request `gmail.send`. CritiqAI uses a Human-in-the-Loop (HITL) gate: the Report Agent creates a draft, the teacher reviews and approves it, and only then is the email sent manually. Auto-send is intentionally disabled.

**Setup steps:**

1. Add the `gmail.compose` scope to the OAuth consent screen
2. Set in `.env`:
   ```dotenv
   TEACHER_EMAIL=teacher@school.edu
   GMAIL_MCP_URL=http://localhost:3002/mcp/sse
   ```

---

### 4. argument-scorer MCP (custom FastMCP server — Cloud Run)

**Purpose:** Score the logical structure of student arguments using a hybrid strategy: deterministic keyword matching for English (0 LLM tokens) and a single compact Gemini call for non-English text (vi/ja/zh, ~300 tokens total, LRU-cached).

**Type:** Custom FastMCP server. Deployed as a standalone **Cloud Run service** in production. For local development, falls back to a direct Python import of `rubric.py` (no subprocess, no port).

**Production — deploy to Cloud Run:**

```bash
# Build from mcp_servers/argument_scorer/Dockerfile
gcloud builds submit mcp_servers/argument_scorer/ \
  --tag REGION-docker.pkg.dev/PROJECT/critiqai/argument-scorer:latest

gcloud run deploy argument-scorer \
  --image REGION-docker.pkg.dev/PROJECT/critiqai/argument-scorer:latest \
  --platform managed \
  --region REGION \
  --port 8080 \
  --no-allow-unauthenticated

# Copy the resulting URL and set it on the main web_app service:
gcloud run services update critiqai-web \
  --update-env-vars SCORER_URL=https://argument-scorer-xxx.run.app
```

**Local development:**

No setup required. When `SCORER_URL` is not set, `mcp_client.py` falls back to importing
`rubric.py` directly (inline Python, zero subprocess, zero port).

To test the MCP server itself locally:

```bash
cd mcp_servers/argument_scorer
python server.py   # stdio mode — ADK connects automatically
```

---

## Environment Variables

All variables are read from the `.env` file in the project root at startup. Copy `.env.example` to `.env` and fill in values.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `GOOGLE_API_KEY` | **Required** | — | API key from Google AI Studio (aistudio.google.com) |
| `GOOGLE_OAUTH_CLIENT_ID` | **Required** | — | OAuth 2.0 client ID for Drive / Sheets / Gmail MCP |
| `GOOGLE_OAUTH_CLIENT_SECRET` | **Required** | — | OAuth 2.0 client secret |
| `DRIVE_MCP_URL` | **Required** | `http://localhost:3000/mcp/sse` | Google Drive MCP server SSE endpoint |
| `SHEETS_MCP_URL` | **Required** | `http://localhost:3001/mcp/sse` | Google Sheets MCP server SSE endpoint |
| `GMAIL_MCP_URL` | **Required** | `http://localhost:3002/mcp/sse` | Gmail MCP server SSE endpoint |
| `DEBATE_LOG_SHEET_ID` | **Required** | — | Google Sheets spreadsheet ID for session history |
| `DEBATE_LOG_RANGE` | Optional | `Sheet1!A:G` | Sheet range for appending debate rows |
| `TEACHER_EMAIL` | **Required** | — | Teacher's email address for drafted report delivery |
| `SCORER_URL` | Optional | — | Cloud Run URL for argument-scorer service (e.g. `https://argument-scorer-xxx.run.app`). When set, scoring uses HTTP instead of stdio subprocess. |
| `GEMINI_MODEL` | Optional | `gemini-2.5-flash-lite` | Override the primary Gemini model |
| `GEMINI_SANDBOX` | Optional | `docker` | Antigravity terminal sandbox mode |
| `SHOW_STUDENT_RESULTS` | Optional | `false` | Show debate scores to students after session ends (`true`/`false`). Togglable from the Teacher dashboard without restart. |

**Example `.env` file:**

```dotenv
# AI Credential
GOOGLE_API_KEY=AIza...

# OAuth (shared across Drive / Sheets / Gmail MCP)
GOOGLE_OAUTH_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...

# MCP server endpoints (SSE)
DRIVE_MCP_URL=http://localhost:3000/mcp/sse
SHEETS_MCP_URL=http://localhost:3001/mcp/sse
GMAIL_MCP_URL=http://localhost:3002/mcp/sse

# Google Sheets log
DEBATE_LOG_SHEET_ID=1xYz...
DEBATE_LOG_RANGE=Sheet1!A:G

# HITL report delivery (draft only — never auto-sent)
TEACHER_EMAIL=teacher@school.edu

# Antigravity sandbox
GEMINI_SANDBOX=docker
```

---

## Installation

### Step 1 — Clone the repository and create a virtual environment

```bash
git clone https://github.com/your-org/CritqAI.git
cd CritqAI
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

Key packages installed:

| Package | Purpose |
| --- | --- |
| `google-adk` | Google Agent Development Kit — core agent framework |
| `fastmcp` | Framework for the argument-scorer local MCP server |
| `google-auth-oauthlib` | OAuth 2.0 flow for Drive, Sheets, and Gmail MCP servers |

### Step 3 — Copy and configure the `.env` file

```bash
cp .env.example .env
# Edit .env with your credentials and IDs
```

### Step 4 — One-time agents-cli setup

```bash
agents-cli setup
```

---

## GCP Deployment

This section covers deploying CritiqAI to **Google Cloud Run** from scratch — creating the GCP project, building Docker images, and wiring all services together.

### Prerequisites

| Tool | Install |
| --- | --- |
| `gcloud` CLI | [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) |
| Docker Desktop | [docs.docker.com/get-docker](https://docs.docker.com/get-docker) |
| Python 3.11+ | Already required for local dev |

Authenticate and select your project:

```bash
gcloud auth login
gcloud auth configure-docker REGION-docker.pkg.dev   # e.g. asia-northeast1-docker.pkg.dev
```

---

### Step 1 — Create a GCP Project

```bash
gcloud projects create YOUR_PROJECT_ID --name="CritiqAI"
gcloud config set project YOUR_PROJECT_ID

# Link billing account (required for Cloud Run)
gcloud billing accounts list                          # find your BILLING_ACCOUNT_ID
gcloud billing projects link YOUR_PROJECT_ID \
  --billing-account=BILLING_ACCOUNT_ID
```

> **Note:** Cloud Run has a generous free tier (2 million requests/month). Billing is required to enable the service but typical classroom usage stays within free limits.

---

### Step 2 — Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  gmail.googleapis.com
```

---

### Step 3 — Create Artifact Registry Repository

All Docker images are stored in a single Artifact Registry repository:

```bash
gcloud artifacts repositories create critiqai \
  --repository-format=docker \
  --location=REGION \
  --description="CritiqAI container images"
```

Replace `REGION` with your preferred region (e.g. `asia-northeast1`, `us-central1`).

---

### Step 4 — Store Secrets in Secret Manager

Never pass sensitive values as plain env vars in Cloud Run. Store them in Secret Manager first:

```bash
# Google AI Studio key
echo -n "AIza...your_key..." | gcloud secrets create GOOGLE_API_KEY --data-file=-

# OAuth credentials
echo -n "123...apps.googleusercontent.com" | gcloud secrets create GOOGLE_OAUTH_CLIENT_ID --data-file=-
echo -n "GOCSPX-..." | gcloud secrets create GOOGLE_OAUTH_CLIENT_SECRET --data-file=-

# Sheets log
echo -n "1xYz...your_sheet_id..." | gcloud secrets create DEBATE_LOG_SHEET_ID --data-file=-

# Teacher email
echo -n "teacher@school.edu" | gcloud secrets create TEACHER_EMAIL --data-file=-
```

Grant the default Cloud Run service account access to read secrets:

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

for SECRET in GOOGLE_API_KEY GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET \
              DEBATE_LOG_SHEET_ID TEACHER_EMAIL; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

### Step 5 — Deploy argument-scorer (MCP sidecar)

```bash
# Build and push image
gcloud builds submit mcp_servers/argument_scorer/ \
  --tag REGION-docker.pkg.dev/YOUR_PROJECT_ID/critiqai/argument-scorer:latest

# Deploy to Cloud Run (private — only critiqai-web calls it)
gcloud run deploy argument-scorer \
  --image REGION-docker.pkg.dev/YOUR_PROJECT_ID/critiqai/argument-scorer:latest \
  --platform managed \
  --region REGION \
  --port 8080 \
  --no-allow-unauthenticated \
  --memory 256Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3
```

Save the resulting service URL — you will need it in Step 6:

```bash
SCORER_URL=$(gcloud run services describe argument-scorer \
  --region REGION --format "value(status.url)")
echo $SCORER_URL   # e.g. https://argument-scorer-abc123-an.a.run.app
```

---

### Step 6 — Deploy critiqai-web (main app)

```bash
# Build and push image
gcloud builds submit . \
  --tag REGION-docker.pkg.dev/YOUR_PROJECT_ID/critiqai/critiqai-web:latest

# Deploy — secrets mounted as env vars, SCORER_URL passed directly
gcloud run deploy critiqai-web \
  --image REGION-docker.pkg.dev/YOUR_PROJECT_ID/critiqai/critiqai-web:latest \
  --platform managed \
  --region REGION \
  --port 8000 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --set-secrets=GOOGLE_API_KEY=GOOGLE_API_KEY:latest,\
GOOGLE_OAUTH_CLIENT_ID=GOOGLE_OAUTH_CLIENT_ID:latest,\
GOOGLE_OAUTH_CLIENT_SECRET=GOOGLE_OAUTH_CLIENT_SECRET:latest,\
DEBATE_LOG_SHEET_ID=DEBATE_LOG_SHEET_ID:latest,\
TEACHER_EMAIL=TEACHER_EMAIL:latest \
  --set-env-vars \
    SCORER_URL=$SCORER_URL,\
    DEBATE_LOG_RANGE=Sheet1!A:G,\
    DRIVE_MCP_URL=http://localhost:3000/mcp/sse,\
    SHEETS_MCP_URL=http://localhost:3001/mcp/sse,\
    GMAIL_MCP_URL=http://localhost:3002/mcp/sse,\
    SHOW_STUDENT_RESULTS=false
```

> **MCP servers (Drive / Sheets / Gmail):** These run as OAuth-authenticated local servers. On Cloud Run they should be deployed as separate sidecars or replaced with direct API calls using a service account. The `*_MCP_URL` vars above point to `localhost` as placeholders — update them to the actual deployed MCP endpoints if you deploy those services.

---

### Step 7 — Verify the deployment

```bash
# Get the public URL for critiqai-web
WEB_URL=$(gcloud run services describe critiqai-web \
  --region REGION --format "value(status.url)")
echo $WEB_URL

# Check logs for startup errors
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=critiqai-web" \
  --limit=50 --format="value(textPayload)"
```

Open `$WEB_URL/teacher` (teacher dashboard) and `$WEB_URL/student` (student debate view) in a browser. Both pages loading confirms a successful deployment.

---

### Updating an existing deployment

After code changes, rebuild and redeploy. Run from the `CritqAI/` root directory.

**PowerShell (Windows):**

```powershell
# argument-scorer (thay đổi rubric/server.py)
gcloud builds submit mcp_servers/argument_scorer/ `
  --tag us-central1-docker.pkg.dev/feednotebooklm/critiqai/argument-scorer:latest `
  --project feednotebooklm
gcloud run deploy argument-scorer `
  --image us-central1-docker.pkg.dev/feednotebooklm/critiqai/argument-scorer:latest `
  --region us-central1 --project feednotebooklm

# critiqai-web (thay đổi app code)
gcloud builds submit . `
  --tag us-central1-docker.pkg.dev/feednotebooklm/critiqai/critiqai-web:latest `
  --project feednotebooklm
gcloud run deploy critiqai-web `
  --image us-central1-docker.pkg.dev/feednotebooklm/critiqai/critiqai-web:latest `
  --region us-central1 --project feednotebooklm
```

**bash/WSL:**

```bash
# argument-scorer
gcloud builds submit mcp_servers/argument_scorer/ \
  --tag us-central1-docker.pkg.dev/feednotebooklm/critiqai/argument-scorer:latest \
  --project feednotebooklm && \
gcloud run deploy argument-scorer \
  --image us-central1-docker.pkg.dev/feednotebooklm/critiqai/argument-scorer:latest \
  --region us-central1 --project feednotebooklm

# critiqai-web
gcloud builds submit . \
  --tag us-central1-docker.pkg.dev/feednotebooklm/critiqai/critiqai-web:latest \
  --project feednotebooklm && \
gcloud run deploy critiqai-web \
  --image us-central1-docker.pkg.dev/feednotebooklm/critiqai/critiqai-web:latest \
  --region us-central1 --project feednotebooklm
```

> Mỗi lần deploy mất khoảng 2–3 phút.

---

### GCP variable cheat sheet

| Placeholder | Example value | Where to get it |
| --- | --- | --- |
| `YOUR_PROJECT_ID` | `critiqai-prod` | `gcloud projects list` |
| `REGION` | `asia-northeast1` | Choose closest to users |
| `BILLING_ACCOUNT_ID` | `01ABCD-EF1234-GHIJ56` | `gcloud billing accounts list` |

---

## Verification

Start the argument-scorer MCP server in a separate terminal:

```bash
source venv/bin/activate
cd mcp_servers/argument_scorer
python server.py
```

Then launch the ADK playground:

```bash
agents-cli playground
```

The web UI will be available at `http://localhost:8000/teacher` (teacher dashboard) and `http://localhost:8000/student` (student debate view). If both pages load and the MCP servers are connected, the environment is configured correctly.

---

## Common Issues

### 1. OAuth token expired

**Symptom:**

```text
google.auth.exceptions.RefreshError: Token has been expired or revoked.
```

**Fix:**

Delete the cached token and re-authenticate:

```bash
rm -f token.json
```

Restart the application. The OAuth consent screen will open in your browser automatically.

---

### 2. Free tier rate limit hit

**Symptom:**

```text
google.api_core.exceptions.ResourceExhausted: 429 Quota exceeded for quota metric
'generate_content_request_count'
```

**Fix options:**

- **Automatic fallback:** `model_config.py` tries models in order: `gemini-2.5-flash-lite` → `gemini-2.0-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash`. If one quota is exhausted the next model is tried automatically.
- **Wait:** Google AI Studio free tier resets quotas per minute and per day. Wait 60 seconds and retry.
- **Override primary model:** Set `GEMINI_MODEL=gemini-2.5-flash-lite` in `.env` to pin to the most quota-friendly model.

---

### 3. argument-scorer not reachable on GCP

**Symptom:**

```text
argument-scorer HTTP unavailable (Connection refused) — dùng fallback trực tiếp
```

**Fix:**

Verify the Cloud Run service is running and `SCORER_URL` is set correctly:

```bash
gcloud run services describe argument-scorer --region REGION --format "value(status.url)"
# Copy the URL and confirm it matches SCORER_URL in your main service's env vars
gcloud run services describe critiqai-web --region REGION \
  --format "value(spec.template.spec.containers[0].env)"
```

If the service is stopped, redeploy:

```bash
gcloud run deploy argument-scorer \
  --image REGION-docker.pkg.dev/PROJECT/critiqai/argument-scorer:latest \
  --port 8080 --no-allow-unauthenticated
```

> **Note for local dev:** `SCORER_URL` is not required. When unset, scoring falls back to a direct
> Python import of `rubric.py` — no subprocess, no port needed.

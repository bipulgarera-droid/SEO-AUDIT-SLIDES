# SEO Audit Dashboard

Standalone SEO audit dashboard with DataForSEO integration and Google Slides generation.

## Features

- 🔍 **Domain Audits** - Full technical SEO audit using DataForSEO
- 📊 **Keyword Analysis** - Organic keyword rankings and traffic estimates
- 🔗 **Backlink Analysis** - Referring domains and backlink metrics
- ⚡ **PageSpeed Insights** - Core Web Vitals and performance scores
- 📑 **Auto-Generated Slides** - Export audit as Google Slides presentation

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required credentials:
- **Supabase**: Project URL and Service Role Key
- **DataForSEO**: API login and password

### 3. Run Locally

```bash
python api/index.py
```

Open http://localhost:3000

## Deployment (Railway)

1. Push this folder to a new GitHub repository
2. Connect to Railway
3. Set environment variables in Railway dashboard
4. Deploy

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Audit Dashboard UI |
| GET | `/api/get-projects` | List all projects |
| POST | `/api/create-audit` | Start new audit |
| GET | `/api/deep-audit/status/:task_id` | Check audit status |
| GET | `/api/audits` | List all audits |
| GET | `/api/audits/:id` | Get audit details |
| POST | `/api/deep-audit/slides` | Generate slides |

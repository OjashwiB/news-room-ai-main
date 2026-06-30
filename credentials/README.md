# Credentials

This directory holds OAuth tokens and API credential files required by the Newsroom AI.

**None of these files are committed to the repository.** They are listed in `.gitignore`.
You must create them yourself by following the setup instructions below.

---

## Required Files

| File | Used by | How to obtain |
|------|---------|---------------|
| `youtube_client_secrets.json` | Publisher agent | Google Cloud Console — see below |
| `youtube_token.pickle` | Publisher agent | Auto-generated on first run |

---

## YouTube Setup

The Publisher agent uploads finished videos to YouTube using the YouTube Data API v3.

### Step 1 — Enable the API

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or select an existing one)
3. Go to **APIs & Services → Library**
4. Search for **YouTube Data API v3** and click **Enable**

### Step 2 — Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth 2.0 Client ID**
3. Application type: **Desktop app**
4. Give it a name (e.g. "Newsroom AI")
5. Click **Create**
6. Click **Download JSON**
7. Rename the downloaded file to `youtube_client_secrets.json`
8. Move it into this `credentials/` directory

### Step 3 — Authorize on first run

On the first production run that reaches the Publisher step, a browser window will open asking you to sign in with your Google account and grant YouTube upload permissions.

After you approve, the token is saved automatically to:
```
credentials/youtube_token.pickle
```

Subsequent runs use the saved token. If it expires, delete the `.pickle` file and re-run to re-authorize.

### OAuth Consent Screen

If you see a "This app is not verified" warning during authorization:
1. Go to **APIs & Services → OAuth consent screen**
2. Add your Google account as a **Test user**
3. Re-run the authorization flow

---

## HeyGen

HeyGen credentials are stored in `.env` — not in this directory.

```env
HEYGEN_API_KEY="sk_..."
HEYGEN_AVATAR_ID="..."   # Not required — anchors are configured in config/anchors.py
HEYGEN_VOICE_ID="..."    # Not required — anchors are configured in config/anchors.py
```

Get your API key from [app.heygen.com/settings](https://app.heygen.com/settings?nav=API).

---

## Summary

After setup, this directory should contain:

```
credentials/
  README.md                    ← this file (committed)
  youtube_client_secrets.json  ← you create this (gitignored)
  youtube_token.pickle         ← auto-generated on first run (gitignored)
```




<!-- 

python tools/earthquake_tool.py simulate

------------------------------

once main is run:

curl -X POST http://localhost:8091/produce/async -H "Content-Type: application/json" -d "{\"request\": \"[SHOW: breaking-news] EARTHQUAKE ALERT — A magnitude 5.5 earthquake has been detected 8km NE of Sacramento. Please produce an urgent breaking news broadcast alerting first responders immediately.\"}"

curl http://localhost:8091/job/JOBID 

-->

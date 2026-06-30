# Newsroom AI

An AI-powered broadcast newsroom that researches topics, fact-checks articles, writes news content, produces broadcast anchor scripts, generates AI anchor videos via HeyGen, and publishes to YouTube — all orchestrated by an Executive Producer agent.

Designed to run as a standalone backend service called by [Jarvis](https://github.com/lenger06/jarvis-assistant-ai) or any other client via a simple HTTP API.

---

## Example Prompts

These can be sent directly to `POST /produce` or spoken to Jarvis naturally.

### Research Only

```
Research the latest developments in the US-China trade war
Find information about the recent OPEC production cuts
What do we know about the SpaceX Starship test flight?
Research key figures and background on the Iran nuclear negotiations
```

### Write an Article

```
Write a news article about the Fed rate decision today
Cover the story of the NATO summit in Brussels
Write a story about the Supreme Court ruling on immigration
Write a news article on the latest White House press briefing
```

### Full Production (Article + Script, no video)

```
Produce a full news segment on the Strait of Hormuz shipping situation
Full production on the Israel-Hamas ceasefire negotiations
Produce a broadcast segment covering the G7 summit outcomes
News segment on the latest Congressional budget vote
```

### Broadcast Video (Full pipeline → YouTube)

```
Generate a news video about the Fed rate decision
Produce a broadcast video on the Iran conflict and publish it to YouTube
Create a news video covering the Supreme Court's latest ruling — have Shawn Green read it
Generate a video on the White House press conference — have Daniel Mercer anchor it
Produce a broadcast video on the rescue of the downed pilots — have Darlene Smith read it
Publish a news video on the latest developments in Ukraine
```

### Special Report (Long-form, in-depth)

```
[SHOW: special-report] Do an in-depth special report on the New Glenn rocket development and the Blue Origin explosion. Make it approximately 15 minutes.
Special report on the history and future of US nuclear policy — serious tone, 10 minutes
Do a deep dive on the opioid crisis — causes, current state, and what comes next
```

Special reports default to 10 minutes if no duration is specified. The pipeline runs the same steps as a Broadcast Video but with extended research (8–10 search angles), a long-form analytical article format, and a script written to fill the full target duration.

### Script Only (when you already have article content)

```
Write a script only — here is the article: [paste article text]
Turn this into a broadcast script: [paste content]
Script only for this story: [paste text]
```

### Video From Script (when you already have a script)

```
Generate a video from this script — have Shawn Green read it: [paste script]
Record this script with Daniel Mercer: [paste script]
Video from script, use Alexa Chen: [paste script]
```

### Requesting a Specific Anchor

```
Produce a broadcast video on the Iran war — have Shawn Green read it
Generate a news video with Darlene Smith anchoring
Alexa Chen should read the entertainment roundup
Have Daniel Mercer anchor the White House briefing video
```

> If no anchor is specified, the Executive Producer selects the anchor assigned to the active show and desk.

---

## Shows & Scheduling

The Executive Producer auto-detects the active broadcast based on time of day and day of week:

| Show | Slug | Trigger | Tone |
|------|------|---------|------|
| Morning Report | `morning-report` | Weekdays before 1 pm | Conversational and upbeat |
| Evening News | `evening-news` | Weekdays 1 pm–midnight | Serious and authoritative |
| Weekend Roundup | `weekend-roundup` | Saturdays and Sundays | Measured and reflective |
| Entertainment Weekly | `entertainment-weekly` | Scheduled explicitly | Upbeat and conversational |
| Special Report | `special-report` | "special report", "deep dive", "in-depth", "long-form" | Measured, thorough, and authoritative |
| Breaking News | `breaking-news` | Breaking News Checker agent | Urgent and direct |

Each show defines which anchor covers which desk and can specify a look preference (formal, casual, sitting, etc.). To override the auto-detected show, prefix your request with `[SHOW: slug]`:

```
[SHOW: special-report] In-depth report on the future of nuclear energy
[SHOW: breaking-news] Alert: major earthquake reported in Tokyo
```

Show definitions live in `config/shows.py`.

---

## Anchor Roster & Look Rotation

Anchors are defined in `config/anchors.py`. Each anchor has an on-air name, one or more `AvatarLook` entries (avatar IDs from HeyGen), a voice ID, and a bio.

The Executive Producer selects the anchor assigned to the active show and desk, then rotates through that anchor's looks round-robin on each production. A `look_preference` (e.g. "formal", "casual") filters the rotation pool to matching looks. Shows can also configure a stand-in anchor that rotates in every N productions (`alt_anchor_name` / `alt_every`).

**Current roster:**

| On-air name | HeyGen actor | Desks |
|---|---|---|
| Shawn Green | Shawn (3 looks) | Politics, National, Foreign, Special Reports |
| Daniel Mercer | Daniel Mercer | National, Politics, Foreign (Morning Report lead) |
| Nicholas Stavros | Kurt | National (Evening News lead) |
| Dominic Fairchild | Man in the Sport Coat | Politics, National |
| Alexa Chen | Alexa | Entertainment |
| Monica Hayes | Saskia (3 looks) | Entertainment |
| Valerie Brooks | Candace (2 looks) | Entertainment |
| Zayne Carter | Zayne (2 looks) | Entertainment |
| Karoline Faye | Brooklyn (2 looks) | Entertainment |
| Victor Marinos | Ricardo (3 looks) | Politics |
| Brandon Jones | Brandon in Grey Suit | Business |
| Alister Blackwood | Dexter Suit Front | Investigative |
| Darlene Smith | Crystal Veil | Health & Science |

To add an anchor, add an entry to the `ANCHORS` list in `config/anchors.py`. Each look is an `AvatarLook(avatar_id, description)` — HeyGen names are noted in comments next to each ID:

```python
Anchor(
    name="Jordan Lee",
    avatars=[
        AvatarLook("avatar_id_here", "formal suit, news desk — hard news"),  # HeyGen: "Avatar Name"
    ],
    voice_id="voice_id_here",
    desk="national",
    bio="Warm and conversational. Strong on human interest stories.",
)
```

Get IDs by calling with your HeyGen API key:
- `GET https://api.heygen.com/v2/avatars`
- `GET https://api.heygen.com/v2/voices`

---

## Agent Roles

### Executive Producer
The orchestrator. Receives every production request, determines the appropriate workflow, auto-detects the active show, selects and rotates anchors per show schedule, and delegates to the team in sequence. Aborts the pipeline early if the Researcher returns no usable content (Tavily unavailable or rate-limited) rather than producing and publishing an empty broadcast. Saves a full production log to `./output/{show_slug}/{run_id}/production_logs/` at the end of every run.

### Breaking News Checker
A background monitor (runs via Jarvis scheduler) that checks for significant breaking news every 30 minutes. Uses an LLM to evaluate whether current events meet broadcast-worthy criteria — major political events, natural disasters, crashes, explosions, corporate collapses, and more. When a qualifying story is detected, it triggers an immediate Breaking News production.

Deduplication and rate-limiting:
- **24-hour dedup window** — all breaking news covered in the last 24 hours is passed to the LLM as context; ongoing conflicts and developing stories stay visible for a full day
- **60-minute cooldown** — minimum gap between any two productions regardless of topic
- **Ongoing conflict rule** — if a story shares 2+ keywords with a recent log entry, the LLM requires a dramatic, unambiguous escalation (war declared, head of state killed, ceasefire signed) before qualifying a new production; routine updates and slight headline variations are suppressed
- **Same-story suppression (code-level)** — even after the LLM approves a story, a tiered per-story cooldown enforces a hard gate based on how many times the same story (2+ keyword overlap) has already fired in the last 24 hours: 3-hour gap after 2+ fires; 6-hour gap after 4+ fires. Prevents a single developing event (earthquake, ongoing conflict) from re-firing every 60 minutes regardless of how the LLM evaluates it

Criteria are defined in `agents/breaking_news_checker/prompts.py`. The coverage log is persisted to `./output/breaking_news_log.json`.

### Researcher
Gathers source material using real-time web search (Tavily). Searches for multiple angles — latest developments, background context, key figures, and statistics. Compiles a sourced research brief with URLs. Also sources b-roll media: still images via Tavily and short video clips via the Pixabay API (if configured). Outputs a `## SOURCED B-ROLL IMAGES` and `## SOURCED B-ROLL VIDEOS` section for the script writer to choose from.

In Special Report mode: runs 8–10 searches across seven angles (latest developments, historical timeline, key figures, expert analysis, opposing viewpoints, economic/social impact, and international context) to build a research brief comprehensive enough to support a 10+ minute broadcast.

### Writer
Receives the research brief and writes a polished news article. Standard productions target 400–600 words in broadcast style (inverted pyramid, active voice, short sentences). When a target duration is specified, the word count scales proportionally (~150 words per minute). Includes a branded dateline. Saves to `./output/{show_slug}/{run_id}/articles/`.

In Special Report mode: writes a long-form analytical piece structured as Executive Summary → Background & Context → Key Developments → Multiple Perspectives & Expert Analysis → Implications & What's Next → Conclusion. May add explanatory context and analytical commentary beyond the raw research facts to fill the target word count.

### Fact Checker
Reads the draft article and verifies key factual claims using web search. Priority check: confirms the current title and status of every named political figure, head of state, and official — "former" applied to a sitting official is a broadcast-level error. Produces a Fact Check Report with three sections — **Verified**, **Unverified**, and **Corrections Needed** — and issues one of three verdicts:
- `CLEAR TO PUBLISH` — all significant claims verified
- `PUBLISH WITH NOTES` — minor unverified items, no outright errors
- `HOLD FOR CORRECTIONS` — factual errors found, must be fixed before publishing

### Editor
Receives the draft article and the Fact Check Report. Applies every correction listed under Corrections Needed — uses web search to confirm accurate information before making each change. Particular focus on current vs. former titles for political figures and officials. Outputs the complete corrected article plus an editorial note listing every change made. The Script Writer uses this corrected article, not the original draft.

### Script Writer
Converts the editor-reviewed article into a spoken broadcast anchor script. Formats it for on-air delivery: natural spoken English, breath-pause markers, and `[GRAPHIC: ...]` cues for supporting visuals. Places `[BROLL: url | description]` markers for still images and `[BROLL: url | description | video]` markers for video clips — B-roll markers must appear at the very start of each new story segment so the visual switches the instant the topic changes. Uses the selected anchor's name in the sign-off. Target read time scales with the requested duration. Saves to `./output/{show_slug}/{run_id}/scripts/`.

### Anchor
Takes the broadcast script, applies TTS text normalisation (see below), strips formatting markers with a pure-regex cleaner (no LLM pass — prevents refusal text from being read aloud), and submits it to HeyGen using the selected anchor's avatar and voice IDs. For scenes with `[BROLL:]` markers, b-roll media (still images **or** video clips) is composited as a Picture-in-Picture in the upper-left corner of the studio background video using FFmpeg, uploaded as a new HeyGen video asset, and used as the scene background. The PIP preserves the original aspect ratio of the source media. Video clip b-roll loops seamlessly for the duration of the scene. Falls back to a Pillow static image composite if FFmpeg is unavailable (images only). Polls for completion natively in Python (every 30 seconds, up to 10 minutes) — does not rely on the LLM to manage polling. Returns the video URL and thumbnail URL when complete.

### Video Editor
Downloads the completed anchor video from HeyGen, extracts all `[GRAPHIC: ...]` cues from the script, and assembles a `video_package.json` in `./output/{show_slug}/{run_id}/media/` containing the video file path, thumbnail URL, graphic cues, and suggested YouTube metadata.

### Producer
Confirms all output files are saved and compiles a final production summary — article path, script path, video path, topic, and word counts.

### Publisher
Reads `video_package.json` and uploads the finished MP4 to YouTube. The title is the story subject only — newsroom name and show-type prefixes ("Defy Logic News | Morning Report | …", "Breaking News: …", etc.) are stripped, leaving just the headline. Sets the HeyGen thumbnail. Adds the video to the appropriate YouTube playlists (see Playlists below). Uploads exactly once in native Python. Returns the final YouTube URL.

---

## YouTube Playlists

Each uploaded video is automatically added to the relevant YouTube playlists. Assignment is multi-layered:

| Layer | Source | Example |
|-------|--------|---------|
| **Show playlist** | Active show slug | Breaking News → Breaking News playlist |
| **Desk playlist** | Editorial desk | Foreign desk → World News playlist |
| **Anchor playlist** | On-air anchor | Shawn Green → Shawn Green — World Report |
| **Series playlists** | Topic keywords | Defined in `config/playlists.py` |

Show playlists are configured in `SHOW_PLAYLISTS` in `config/playlists.py`. The Breaking News playlist ID is pre-configured. Morning Report, Evening News, Special Reports, and Weekend Roundup playlist IDs can be filled in after creating them in YouTube Studio (Content → Playlists → copy the `PLxxxxxx` ID from the URL).

The EP can also assign extra playlists explicitly via `extra_playlists` in its analysis (e.g. adding a story to a series playlist). All playlist IDs are deduplicated before upload.

---

## TTS Text Normalisation

All anchor script text is normalised before submission to HeyGen via `_normalize_tts()` in `tools/heygen_tool.py`. Prevents common anchor mispronunciations:

- `U.S.` → `U S`, `U.S.A.` → `U S A`, `D.C.` → `D C`, `F.B.I.` → `F B I`, `C.I.A.` → `C I A`
- `vs.` → `versus`, `etc.` → `etcetera`
- `Dr.` → `Doctor`, `Mr.` → `Mister`, `Mrs.` → `Missus`, `Sen.` → `Senator`, `Gov.` → `Governor`, `Gen.` → `General`, `Rep.` → `Representative`
- Em-dash `—` → `, ` (prevents "dash" being read aloud)

To add a new rule, append a tuple to `_TTS_REPLACEMENTS` at the top of `tools/heygen_tool.py`:
```python
(_re.compile(r'\bNATO\b'), "NAY-toh"),
```

---

## Workflows

| Workflow | Trigger phrases | Steps |
|----------|----------------|-------|
| `RESEARCH_ONLY` | "research", "find information about", "what do we know about" | Researcher |
| `ARTICLE` | "write an article", "write a story", "cover this story" | Researcher → Writer → Fact Checker → Editor → Producer |
| `FULL_PRODUCTION` | "full production", "produce a segment", "news segment", "broadcast" | Researcher → Writer → Fact Checker → Editor → Script Writer → Producer |
| `BROADCAST_VIDEO` | "video", "youtube", "record", "generate video", "publish" | Researcher → Writer → Fact Checker → Editor → Script Writer → Anchor → Video Editor → Producer → Publisher |
| `SPECIAL_REPORT` | "special report", "deep dive", "in-depth", "long-form", "comprehensive coverage" | Same steps as BROADCAST_VIDEO with extended research, long-form writing, and full-duration scripting |
| `SCRIPT_ONLY` | "script only", "write a script", "turn this into a script" (with content) | Script Writer → Producer |
| `VIDEO_FROM_SCRIPT` | "video from script", "record this script", "generate video from script" | Anchor → Video Editor → Producer → Publisher |

The pipeline aborts early and logs an error (without publishing) if the Researcher returns no usable content — e.g. when Tavily is rate-limited or unavailable.

Each step receives the full output of all prior steps as context.

---

## Architecture

```
Jarvis (or any HTTP client)
 └─► POST /produce/async
       └─► Executive Producer (orchestrator)
             ├─► Breaking News Checker  — background monitor (Jarvis scheduler)
             ├─► Researcher      — web_research_tool, file_operations_tool
             ├─► Writer          — file_operations_tool
             ├─► Fact Checker    — web_research_tool
             ├─► Editor          — web_research_tool, file_operations_tool
             ├─► Script Writer   — file_operations_tool
             ├─► Anchor          — HeyGen API (generate + native async poll)
             ├─► Video Editor    — video_tools (download, extract cues, package)
             ├─► Producer        — file_operations_tool
             └─► Publisher       — YouTube API (upload once + thumbnail)
```

Output files are saved per-run under a timestamped directory:
```
output/
  {show_slug}/
    {run_id}/
      articles/         — finished news articles (.md)
      scripts/          — broadcast anchor scripts (.md)
      media/            — anchor videos (.mp4) and video_package.json
      production_logs/  — full production logs with all agent outputs (.md)
  last_broadcast.json   — timestamp of the most recent completed production
```

---

## Setup

### Requirements

- Python 3.10+
- OpenAI API key
- Tavily API key
- HeyGen API key *(for Anchor agent — video generation)*
- Google Cloud project with YouTube Data API v3 enabled *(for Publisher agent)*

### Installation

```bash
cd news-room-ai
pip install -r requirements.txt
```

### HeyGen Setup

1. Sign up at [heygen.com](https://heygen.com) and get your API key from **Settings → API**
2. Add anchors to `config/anchors.py` with avatar and voice IDs:
   - Call `GET https://api.heygen.com/v2/avatars` with your API key to list available avatars
   - Call `GET https://api.heygen.com/v2/voices` to list voices

### YouTube Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services → Library**
2. Enable **YouTube Data API v3**
3. Go to **Credentials → Create Credentials → OAuth 2.0 Client ID** (Desktop app)
4. Download the JSON file and save it to `credentials/youtube_client_secrets.json`
5. On first run the Publisher agent will open a browser to authorize — token saved to `credentials/youtube_token.pickle`

See [`credentials/README.md`](credentials/README.md) for full step-by-step setup instructions including OAuth consent screen configuration.

### B-Roll Compositing

The Anchor agent composites b-roll media (still images or video clips) as a Picture-in-Picture overlay on a studio background video using FFmpeg, then uploads the result to HeyGen as a video asset.

- Place background videos in `./assets/` named after their HeyGen video asset ID (e.g. `./assets/f6fa4085043140deaba8258a96233036.mp4`)
- Multiple backgrounds are supported — each desk automatically uses its configured `background_asset_id` from `config/desks.py`; shows can override this with their own background (e.g. Special Report uses a distinct look)
- Requires `imageio-ffmpeg` (already in `requirements.txt` — bundles FFmpeg, no system install needed)
- Composite results are cached in `./cache/broll_composites/`; downloaded video clips cached in `./cache/broll_video_downloads/`
- For video clips, the source footage loops seamlessly for the 15-second composite window HeyGen then loops
- The PIP preserves the original aspect ratio of the source media — no stretching
- Falls back to a Pillow static image composite if FFmpeg is unavailable (images only; video b-roll falls back to studio background)

### Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```env
NEWSROOM_NAME="Defy Logic News"

OPENAI_API_KEY="sk-..."
TAVILY_API_KEY="tvly-..."
PIXABAY_API_KEY=""         # Free at pixabay.com/api — enables video b-roll search

HEYGEN_API_KEY="sk_..."

HOST=0.0.0.0
PORT=8091
DEBUG=True
LOG_LEVEL=INFO

ARTICLES_DIR=./output/articles
SCRIPTS_DIR=./output/scripts
MEDIA_DIR=./output/media
LOGS_DIR=./output/production_logs

YOUTUBE_CLIENT_SECRETS_PATH=credentials/youtube_client_secrets.json
```

---

## Running

```bash
cd news-room-ai
python main.py
```

Server starts at `http://0.0.0.0:8091`.

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info and available workflows |
| `/health` | GET | Agent status |
| `/produce` | POST | Run a production synchronously (blocks until complete) |
| `/produce/async` | POST | Start a production in the background — returns `job_id` immediately |
| `/job/{job_id}` | GET | Poll for the status and result of an async production job |
| `/produce/stream` | POST | Run a production via SSE (streams status updates) |
| `/docs` | GET | Swagger UI |

### Request format

```json
{
  "request": "Produce a full news segment on the situation in the Strait of Hormuz",
  "client_datetime": "Saturday, April 5, 2026, 03:00 PM PDT"
}
```

### Async response (`/produce/async`)

```json
{ "job_id": "e4b130b8-a012-4722-9562-388a9ab7aa4b", "status": "started" }
```

### Job status (`/job/{job_id}`)

```json
{
  "status": "running | complete | error",
  "result": "**Production Complete — BROADCAST_VIDEO**\nTopic: ...",
  "workflow": "BROADCAST_VIDEO",
  "topic": "Strait of Hormuz",
  "error": null
}
```

---

## Calling from Jarvis

Jarvis routes news production requests automatically. Just talk naturally:

```
Jarvis, produce a full news segment on the Iran situation
Jarvis, research the latest on shipping through the Strait of Hormuz
Jarvis, generate a news video about the drone strike near Dubai — have Darlene Smith read it
Jarvis, schedule a daily broadcast video at 6am on the latest White House announcements
Jarvis, write a news article about the SpaceX launch
Jarvis, do a special report on the development of the New Glenn rocket — make it 15 minutes
```

Jarvis responds immediately confirming production has started, then notifies you when the video is published. The newsroom backend must be running at `http://localhost:8091`.

To call the API directly:

```bash
curl -X POST http://localhost:8091/produce/async \
  -H "Content-Type: application/json" \
  -d '{"request": "Write a news article about the Strait of Hormuz shipping situation"}'
```

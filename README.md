<p align="center">
  <img src="frontend/favicon.svg" width="64" height="64" alt="Multimodal Studio">
</p>

<h1 align="center">Multimodal Studio</h1>

<p align="center">
  <strong>Turn any document into a narrated, publish-ready video.</strong><br>
  Drop a chapter, notes, or a topic → pick who it is for → Muse Wonder writes the slides, a studio voice speaks them, Cloud Run serves the app.
</p>

<p align="center">
  <a href="#how-to-use">How to use</a> ·
  <a href="#agentic-ai-architecture--flowchart">Agentic AI & Flowchart</a> ·
  <a href="#agent-harness-screenshots--dashboard">Harness UI</a> ·
  <a href="#real-world-scenarios--sample-artifacts">Scenarios & Samples</a> ·
  <a href="#what-it-can-do">What it can do</a> ·
  <a href="#run-it">Run it</a> ·
  <a href="#configure">Configure</a> ·
  <a href="#how-a-slide-fits-its-content">Slide layouts</a>
</p>

<p align="center">
  <img src="docs/screenshots/studio.png" alt="Studio — upload knowledge, pick a format, run the pipeline" width="100%">
</p>
<p align="center"><sub>Studio: <strong>Studio · History · Image lab · Admin</strong>. Drop a source, pick a format, run Document → Extract → Slides → Voiceover → Video → Publish. There is no login screen; the app opens straight into Studio. The header mark is the Muse launch shape: a white rounded tile and a black M that draws itself.</sub></p>

<p align="center">
  <img src="docs/screenshots/video-cover.png" alt="Opening frame: title and the paper page" width="49%">
  <img src="docs/screenshots/video-cards.png" alt="Sharp cards on the whiteboard" width="49%">
</p>
<p align="center">
  <img src="docs/screenshots/video-stats.png" alt="Readable stat cards" width="49%">
  <img src="docs/screenshots/video-flow.png" alt="A flow the viewer can read" width="49%">
</p>
<p align="center"><sub>A real run of <em>Attention Is All You Need</em>. The opening shows the paper and the title. Cards, numbers, and the flow stay sharp after a short draw-on. The frame the video holds is the settled pose, not a blurred entrance.</sub></p>

## AI Builder Cup submission

**Team:** Multimodal Studio  
**Leader:** M Sai Teja (leads and built it)  
**Member:** Anil Kumar

**Pitch deck:** `Template/Out/Multimodal Studio - AI Builder Cup.pptx` (filled from the official template).

**What we built.** Multimodal Studio turns a chapter, notes, or a topic into a video a student can replay. Muse Wonder reads the source and writes the slides. Kokoro speaks them. The highlight walks with the sentence. Slides are filmed at 2x and the held frame is the sharp pose, so the picture does not sit in the blur of the entrance. Jobs, costs, and memory stay in SQLite on disk.

**Who it is for.** A teacher who does not want to rebuild every PDF as slides. A tutor. A student revising. A parent walking through homework. The same path also fits a creator, but the first job is learning that is actually watchable.

**Live now.** GitHub: https://github.com/saitej123/Muse-Multimodal-Studio · App: https://multimodal-studio-469528918286.us-central1.run.app (no login).

**What we want next.** A simpler Studio. Handwritten teaching templates. Manim-style motion for formulas. Predefined YouTuber looks and a custom one. Better animation models, both shipped and added by the teacher. New animation skills you can pick the way you pick a style today.

**How the required products are used.**

| Product | Role in this submission |
| --- | --- |
| **Muse** | Text and vision on `muse-wonder-1.0` (briefs on `muse-spark-1.3`) through the OpenAI-compatible Responses API at `https://api.meta.ai/v1`. Page images, PDF, audio, and video go in as content parts. Web research uses the `web_search` tool. Thumbnails on `muse-image-1.0`. The assistant listens with `muse-voice-transcribe-1.0`. Narration is local Kokoro, with Kyutai pocket-tts if Kokoro is not installed, because Model API does not synthesize speech. |
| **Cloud Run** | Hosts the FastAPI container. `deploy/cloudbuild.yaml` builds `Dockerfile` and deploys `multimodal-studio`. |
| **SQLite** | Jobs, cost events, and agent memory live in `workspace/sessions.db` and `workspace/agent_memory.db`. Slide images, audio, and the MP4 stay in that job's workspace folder. |

**The app has no login.** There are no accounts and no sign-in screen. The local URL and the hosted link both open straight into Studio.

**Public links** (keep these up through review). The demo video is the one item still to record: 3 to 4 minutes, one real file becoming an MP4.

| Required item | Rule | Where it comes from |
| --- | --- | --- |
| Pitch deck | Use the prescribed template | `Template/Out/Multimodal Studio - AI Builder Cup.pptx` |
| Demo video | 3 to 4 minutes, showing a real run | Record: open Studio, drop a short PDF, pick Kore, run, play the MP4. Do not exceed 4:00. |
| Deployed prototype | Must stay up during judging | https://multimodal-studio-469528918286.us-central1.run.app |
| GitHub repository | Public source for the whole evaluation | https://github.com/saitej123/Muse-Multimodal-Studio |

Set `MODEL_API_KEY` on the Cloud Run service from Secret Manager. Do not commit `.env`.

---

## What it can do

<table>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/formats.png" alt="Six video formats">
      <br><sub><strong>Six export formats</strong> — YouTube 16:9, Shorts, Reels, TikTok, Square 1:1, LinkedIn. Length chips follow the platform (8 min for long-form, seconds for Shorts).</sub>
    </td>
    <td width="50%">
      <img src="docs/screenshots/visual-styles.png" alt="Visual style layouts">
      <br><sub><strong>Templates</strong> — twelve in all — Whiteboard, Notebook, Chalkboard, Editorial, Magazine, Broadcast, Glass, Bento, Poster, Pop, Cinema, Terminal. Auto picks one and a palette from the document.</sub>
    </td>
  </tr>
  <tr>
    <td>
      <img src="docs/screenshots/voices.png" alt="Voices tab">
      <br><sub><strong>Narration</strong> — 30 studio voices. Preview, then the pipeline uses that voice.</sub>
    </td>
    <td>
      <img src="docs/screenshots/video-cover.png" alt="Opening frame of a generated video">
      <br><sub><strong>Sharp frames</strong> — the opening shows the source page and the title. There is no login screen; the app opens straight in Studio.</sub>
    </td>
  </tr>
</table>

| Capability | What you get |
| --- | --- |
| **Ingest** | PDF, Word, PowerPoint, TXT, Markdown, images — Muse Wonder reads pages, with text fallback |
| **Teach to an audience** | Age group + knowledge level load a teaching prompt you can edit |
| **Plan long docs** | Split a book/paper into topics, research the web, then one video or many |
| **Review** | Duplicate-slide check and voice ↔ highlight sync before you ship |
| **Publish pack** | Titles, captions, tags, thumbnails for YouTube, Instagram, X, LinkedIn, TikTok, Substack, Medium |
| **Image lab** | Muse Image cloud thumbnails plus a prompt-based test generator |
| **C.H.I.T.T.I.** | In-app voice assistant (Muse listens and answers) while you work |
| **Admin** | Color palette, layout-family preview, social credentials, cron papers, costs |
| **History** | Every generated session — reopen, re-run, or delete (fills after you run the pipeline) |
| **Automation** | Admin cron: trending papers (HF / arXiv / Semantic Scholar) → overnight videos |

<p align="center">
  <img src="docs/screenshots/admin.png" alt="Admin dashboard — visual styles preview" width="100%">
</p>
<p align="center"><sub>Admin: Color palette, Visual styles (one frame per layout family), Social, Cron jobs, Costs.</sub></p>

<table>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/history.png" alt="History tab">
      <br><sub><strong>History</strong> — sessions appear here after a pipeline run. Open to review, re-run, or delete.</sub>
    </td>
    <td width="50%">
      <img src="docs/screenshots/image-lab.png" alt="Image lab">
      <br><sub><strong>Image lab</strong> — Muse Image thumbnails and a prompt-based test generator.</sub>
    </td>
  </tr>
</table>

---

## Agentic AI Architecture & Flowchart

Before a single frame is drawn, an **agent harness** (`app/pipeline/agent_harness.py`) plans and checks the deck. It is a bounded controller (a turn budget, `max_turns`, shown live in the admin tab) that calls schema-validated tools, observes each result, repairs what it can, and writes what it learned to memory. Everything below is read from the code, not assumed:

* **What it is, honestly.** The sequence is fixed: inspect the document, recall rules, score a style, draft the deck, audit it, repair if the audit found something fixable, save a run summary. The model writes the slides (`draft_slide_deck`); it does not choose the next tool. That is deliberate: a predictable loop never wanders, never overspends, and always leaves a receipt.
* **Tools.** A typed registry (`tools.get_catalog()`; the Admin → Agent Harness tab lists the live set). Each tool has a parameter schema, errors are caught and returned as data, and only `save_memory` can write. `research_topic_context` and `synthesize_visual_layout` are registered too, but are run on demand from that admin tab, not in the default loop.
* **Self-correction.** The audit checks duplicate headings, repeated visuals and narration pacing. The only repair applied automatically is giving a repeated heading a distinct one (it adds that slide's first on-screen point); the deck is then re-audited and anything left is shown in the review panel rather than guessed at.
* **Memory** (`app/agent_memory.py`): working memory (plan and scratchpad), checkpoint memory (every turn to `agent_trace.jsonl` and a run receipt on the job) and long-term memory (preferences, style rules, feedback). Long-term memory is SQLite on disk.

#### Why this matters for ed-tech, and what it automates

| Without it | With it |
| --- | --- |
| A teacher reads the whole paper to decide what to stress, which style fits, how long each slide should run | `inspect_document` classifies the document, `score_style_and_theme` picks a template and palette, both explained on screen |
| Two slides end up with the same heading or the same bullets, and nobody notices until the video is rendered | The audit runs before rendering, so the expensive steps (voice, capture, encode) never run on a flawed deck |
| Every run starts from zero | `recall_memory` brings back what worked for this kind of document, `save_memory` adds to it, so repeat users get better defaults |
| Something looks wrong and nobody can say why | Every turn has its thought, tool, arguments, result, time and status, viewable per job |

Cost and time stay bounded because the loop has a turn budget and each tool does one thing.

### System Flowchart

```mermaid
flowchart TD
    subgraph Inputs["1. Knowledge Ingestion (no login)"]
        Demo["Studio<br/>(opens straight in)<br/>No accounts"]
        Doc["Document Upload<br/>(PDF, Word, PPT, TXT, Images)"]
        Cron["Admin Cron Topics<br/>(Trending Papers, News, Labs)"]
    end

    subgraph ExtractStage["2. Extraction & Analysis"]
        VLM["VLM & Text Extraction<br/>(Muse Wonder / PyMuPDF)"]
        Analysis["Document Analysis & Tone Classifier<br/>(Equations, Formulas, Complexity)"]
    end

    subgraph AgentHarness["3. Agentic AI Harness (ReAct Loop)"]
        direction TB
        subgraph MemoryTiers["Layered Memory Architecture"]
            WM["Tier 1: Working Memory<br/>(Active Plan Checklist & Scratchpad)"]
            CM["Tier 2: Checkpoint Memory<br/>(Turn Receipts & JSONL Audit)"]
            LTM["Tier 3: Long-Term Memory<br/>(SQLite on disk)"]
        end

        subgraph ToolRegistry["Typed Tool Registry"]
            T1["inspect_document"]
            T2["recall_memory"]
            T3["save_memory"]
            T4["score_style_and_theme"]
            T5["research_topic_context"]
            T6["synthesize_visual_layout"]
            T7["audit_and_fix_slides"]
            T8["draft_slide_deck"]
        end

        ReAct["Bounded controller<br/>Plan ➔ Tool ➔ Observe ➔ Repair"]
        Audit["Quality & Sync Audit Pass<br/>(Duplicate Detection & Dwell Sync)"]
    end

    subgraph VideoPipeline["4. Deterministic Media Synthesis"]
        Narrate["Voiceover Synthesis<br/>(studio neural voice)"]
        Capture["Frame-Seeking Capture<br/>(Playwright Headless Chromium)"]
        Merge["Audio-Video Merge<br/>(FFmpeg Synced MP4)"]
        Publish["Publish Pack & Multi-Platform<br/>(YouTube, Instagram, LinkedIn, TikTok)"]
        Store["Storage: SQLite<br/>(jobs, cost events, agent memory)"]
    end

    Demo --> Doc
    Doc --> VLM
    Cron --> VLM
    VLM --> Analysis
    Analysis --> ReAct

    ReAct <--> MemoryTiers
    ReAct <--> ToolRegistry
    ReAct --> Audit
    Audit --> ReAct
    ReAct -->|Final Deck + Receipt| Narrate

    Narrate --> Capture
    Capture --> Merge
    Merge --> Publish
    Publish --> Store
    Store -. every persist .-> ReAct
```

### Layered Memory & Tool Implementation

| Layer / Tool | Purpose & Engineering Standard |
| --- | --- |
| **Tier 1: Working Memory** | Ephemeral per-session state tracking the active goal, dynamic plan checklist (`[✓] inspect`, `[✓] recall`, `[✓] draft`), and observation buffer. |
| **Tier 2: Checkpoint Memory** | Episodic trace capturing every thought, tool name, argument payload, execution latency, and error state. Persisted to `agent_trace.jsonl`. |
| **Tier 3: Long-Term Memory** | SQLite (`workspace/agent_memory.db`, WAL) holding preferences, document-to-style heuristics and review feedback. |
| **Tool: `inspect_document`** | Deeply inspects document structure, volume, detected mathematical equations, and statistics. |
| **Tool: `recall_memory`** | Queries long-term memory via token and tag matching for audience rules and visual pacing. |
| **Tool: `save_memory`** | Persists run takeaways and user feedback into long-term memory for cross-session adaptation. |
| **Tool: `score_style_and_theme`** | Evaluates document tone against target audience to score layout styles and color palettes. |
| **Tool: `research_topic_context`** | Grounds concepts with live web research. Run on demand from Admin → Agent Harness (topic research for a job runs separately, in the pipeline). |
| **Tool: `synthesize_visual_layout`** | Asks `layout_engine` whether a list of points fits a collision-free geometry. On demand from the admin tab; the renderer runs the same engine for every slide. |
| **Tool: `audit_and_fix_slides`** | Deterministic review for duplicate headings, repeated visuals and narration pacing. The controller repairs repeated headings and re-audits. |
| **Tool: `draft_slide_deck`** | Synthesizes structured slide deck JSON adhering to strict formatting constraints and word budgets. |

### Agent Harness Screenshots & Dashboard

<p align="center">
  <img src="docs/screenshots/harness-flowchart.png" alt="Agentic AI Architecture Flowchart" width="100%">
</p>
<p align="center"><sub><strong>Architecture Flowchart</strong> — Hosted demo or upload, then extract, slides, studio voice, capture. Jobs stay in SQLite.</sub></p>

<table>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/agent-harness-dashboard.png" alt="Agent Harness Dashboard & Memory Explorer">
      <br><sub><strong>Agent Harness &amp; Memory Explorer</strong> — gauges read from the server (turn budget, tool count, memory backend, audit, storage status), namespace filter, and a searchable memory store.</sub>
    </td>
    <td width="50%">
      <img src="docs/screenshots/agent-tools-catalog.png" alt="Tool Registry Catalog">
      <br><sub><strong>Tool Registry</strong> — Schema-validated domain tools with parameter typing and sandboxed dispatch.</sub>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="docs/screenshots/agent-trace-run.png" alt="Turn-by-turn ReAct Execution Trace">
      <br><sub><strong>Turn-by-Turn ReAct Trace</strong> — Inspects document, recalls persistent rules, scores styles, drafts slides, and executes automated self-repair.</sub>
    </td>
  </tr>
</table>

### Real-World Scenarios & Sample Artifacts

#### Scenario 1: AI & Machine Learning Research Paper (ArXiv / HuggingFace)
* **Input Knowledge:** Research PDF on Transformer architecture with attention equations, projection matrices ($W_q, W_k, W_v$), and BLEU score benchmarks.
* **Agent Harness Loop:**
  1. `inspect_document`: Flags academic paper with LaTeX equations and benchmark comparisons.
  2. `recall_memory`: Pulls `style_rules:ml_paper` guideline: *Highlight mathematical formulas, benchmark stats, and core architecture components.*
  3. `score_style_and_theme`: Recommends `teardown` style with `cyber` theme (dark glass, cyan accent, KaTeX formula formatting).
  4. `draft_slide_deck`: Generates multi-beat explainer with embedded LaTeX formulas:
     $$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$
  5. `audit_and_fix_slides`: Confirms no duplicate headings or repeated visuals and checks narration pacing.
  6. `save_memory`: Records session takeaways and citation tags to persistent memory.

```json
{
  "heading": "Scaled Dot-Product Attention",
  "layout": "bullets",
  "equations": ["\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V"],
  "bullets": [
    "Queries and keys of dimension d_k are multiplied",
    "Softmax assigns weights to all value vectors",
    "Multi-head projection runs h attention layers in parallel"
  ],
  "narration": "Rather than calculating a single attention pass, queries, keys, and values are linearly projected into lower-dimensional spaces, allowing the model to attend to information at different representation subspaces simultaneously."
}
```

#### Scenario 2: Strategic Executive Brief & Financial Metrics
* **Input Knowledge:** Executive quarterly review with ARR numbers, churn reduction, and strategic priorities.
* **Agent Harness Loop:**
  1. `inspect_document`: Identifies business memo with critical percentages and currency values.
  2. `recall_memory`: Pulls `style_rules:executive_summary`: *Lead with key business metrics and high-level decision pillars.*
  3. `score_style_and_theme`: Selects `minimal` style with `editorial` palette and weighted layout geometry.
  4. Render: the layout engine reads `weights: [100, 45, 30]` and builds a squarified treemap where retention dominates the visual field.

```json
{
  "heading": "Q3 Growth & Retention Drivers",
  "layout": "bullets",
  "weights": [100, 45, 30],
  "bullets": [
    "Enterprise net revenue retention reached 134%",
    "Self-serve customer acquisition cost dropped 22%",
    "Product-led onboarding reduced time-to-value to 4 days"
  ],
  "narration": "Our enterprise retention was the primary revenue engine this quarter, while self-serve acquisition efficiency gave us positive unit economics across all cohorts."
}
```

#### Scenario 3: Systems Engineering & Cloud Migration Walkthrough
* **Input Knowledge:** Engineering runbook detailing containerized microservice migration to Kubernetes.
* **Agent Harness Loop:**
  1. `inspect_document`: Recognizes technical documentation with step-by-step sequential dependencies.
  2. `recall_memory`: Fetches `style_rules:how_to_tutorial`: *Use ordered milestones with clear step numbers and actionable instructions.*
  3. `score_style_and_theme`: Assigns `blueprint` style with `path` / `cascade` layout geometry.
  4. `audit_and_fix_slides`: Verifies voiceover dwell time so complex technical steps match narration pacing without speech rushing.

```json
{
  "heading": "Zero-Downtime Cluster Migration",
  "layout": "steps",
  "steps": [
    "Provision multi-region control planes",
    "Mirror database traffic with dual writes",
    "Deploy blue-green ingress routing",
    "Cut over DNS and decommission legacy VMs"
  ],
  "narration": "We begin by provisioning independent control planes, mirror real-time database transactions, switch ingress traffic through blue-green proxies, and finalize DNS cutover with zero downtime."
}
```

---

## How to use

1. **Open** `http://127.0.0.1:8001`. There is no login: the app opens in Studio, and the **Admin** tab holds visual styles, cron, and costs.
2. **Studio → drop a file** (or click the dropzone). PDF / Word / PPT / notes / images all work.
3. **Pick a video format** (YouTube, Shorts, Reels, TikTok, Square, LinkedIn) and a **target length**.
4. **Visual style** — leave **Auto**, or pick one of the twelve templates (Whiteboard, Notebook, Chalkboard, Editorial, Magazine, Broadcast, Glass, Bento, Poster, Pop, Cinema, Terminal) and one of 14 color palettes. Admin → Visual styles shows a real render of a sample lesson, made by the same code that films the video.
5. **Audience** — age + knowledge, or leave Auto. Edit the teaching prompt if you want a custom tone.
6. **Voices** — preview a studio voice (default Kore). That voice narrates the whole video.
7. **Run pipeline**. Watch the strip: Document → VLM extract → Slides → Voiceover → Video → Publish.
8. **Review** generated slides for duplicates and voice sync. Tweak extracted text or narration and re-run a stage if needed.
9. **Publish details** — generate per-platform copy, then Post (if credentials are set) or Copy / Download.
10. **History** — every finished (or in-progress) job lands here so you can reopen it later.

**Tip:** for long PDFs, use **Plan topics** first, pick the chapters you want, then run one combined video or one video per topic.

---

## Run it

### Local

Python 3.12, FFmpeg on `PATH` (or the bundled `imageio-ffmpeg` fallback).

```bash
cp -n .env.example .env          # then set MODEL_API_KEY
bash scripts/setup_venv.sh       # uv venv + requirements.txt
source .venv/bin/activate
python run.py                    # http://127.0.0.1:8001
```

Open the URL. There is no sign-in step.

### Docker

```bash
cp -n .env.example .env
docker compose up --build        # http://127.0.0.1:8001
```

GPU thumbnail image: `docker compose --profile gpu up --build`

---

## Configure

`.env` holds only the keys with real values (everything else uses built-in defaults). **Never commit `.env`.** On Cloud Run, set the same keys as service env vars / secrets instead.

| Setting | Purpose |
| --- | --- |
| `MODEL_API_KEY` | Muse Wonder, vision, web search, Muse Image thumbnails, speech-to-text |
| `MUSE_MODEL` | Text and vision. Default `muse-wonder-1.0`. Briefs use `muse-spark-1.3` |
| `MUSE_IMAGE_MODEL` | Thumbnails. Default `muse-image-1.0` |
| `MUSE_TTS_VOICE` | Kokoro studio voice id. Default `Kore` (`af_kore`) |
| `YOUTUBE_CLIENT_SECRETS` | Path to OAuth client JSON for YouTube upload |
| `AUTO_ENABLED` | Nightly paper → video scheduler (admin) |

Social posting tokens live in `workspace/social_credentials.json` (admin UI), not in git.

**Where data lives.**

| Data | Where it lives |
| --- | --- |
| Jobs and history | SQLite `workspace/sessions.db` |
| Slide images, audio, MP4 | `workspace/<job>/` on disk |
| Cost and usage events | SQLite `usage_events` in `workspace/sessions.db` |
| Agent long-term memory | SQLite `workspace/agent_memory.db` |

Admin → Cost tracker reads that SQLite file, and Admin → Agent Harness shows the storage card. The cost report uses Muse token counts when the response carries them, and attributes spend from parallel slide and voice calls to the job that made them.

---

## How a slide fits its content

The same notes do not get a recoloured copy of one card stack. Each slide is laid out from its own items — how many there are, how long each line is, and an optional importance score — so the geometry changes with the data. The template you pick (twelve families, each with three slide layouts) sets the structure, motion and font pair; slides in one deck move differently from each other. Type is sized per slide so the frame is used end to end. To add a template, add a style entry in `app/video_options.py`, map it to a family in `app/pipeline/edu_theme.py` (`EDU_FAMILY_MAP`, `FAMILY_INFO`); a whole new family is a CSS block plus fonts in `app/pipeline/edu_families_extra.py`, and it appears in the picker with a live preview.

| What you drop in | What you see |
| --- | --- |
| Four short takeaways | A treemap, an orbit, a stair, or a pinned-note scatter — whichever that style leads with, and a different one on the next slide |
| One idea much more important than the rest | That line gets the large cell; the others shrink around it |
| Three numbers (`98%`, `120ms`, `12,000 docs`) | Bar height or tile area follows the number, not a fixed three-column template |
| Ordered steps | A path, a cascade, or stacked bands, so reading order stays obvious |
| A slide with narration and no bullets | Short phrases are pulled from the narration and laid out the same way |
| A quote, diagram, or before/after | Those keep their own frame; the fitter does not restyle them |

Give a bullets slide a `weights` list (0–100, one score per bullet) when you want size to follow importance instead of sentence length:

```json
{
  "heading": "What actually moved retention",
  "layout": "bullets",
  "weights": [100, 40, 25],
  "bullets": [
    "Weekly review cut churn in half",
    "Onboarding email helped a little",
    "A redesigned logo did not"
  ],
  "narration": "The weekly review mattered most. The email helped. The logo did not."
}
```

Families the fitter can draw: treemap, orbit, cascade, masonry, path, golden split, bands, scatter, slices, skyline. A deck will not repeat a geometry, and it will not use the same family on two slides in a row.

Check it locally:

```bash
.venv/bin/python scripts/check_layout_engine.py
```

---

## Layout

```
app/            FastAPI, pipeline, auth, automation
frontend/       Studio SPA
pitch/          Capstone deck
Template/      Official AI Builder Cup deck and the filled copy in Template/Out
deploy/        Cloud Run build (cloudbuild.yaml)
docker/         Container entrypoint
scripts/        setup_venv.sh, e2e
docs/screenshots/
.env.example    Template only — real secrets stay in .env
```

Runtime data is local and gitignored: `workspace/` (jobs + `sessions.db`), `models/` (TTS weights), `logs/`, `automation_output/`.

---

<p align="center">
  <sub>Multimodal Studio · AI Builder Cup · Anil Kumar · M Sai Teja</sub>
</p>

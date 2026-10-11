# TEPHRA research: Ask TEPHRA (chat/voice), Gemini "satellite eyes", shift handover, and UI for the 8 new AI features

Date: 2026-10-11. Tags: [C] = I opened the page and it says this. [R] = a secondary source says it. UNVERIFIED = not confirmed. Existing research was skimmed (10, 15, 08, 06, UI-DESIGN). This report does not repeat 10's model table or 08's judging criteria. It uses their facts where needed.

Search limits: WebFetch could not read skybrary.aero (it returned a "SuperJS check" stub) or the EUMETSAT user portal (JavaScript only). The NASA/JPL handover PDF failed to download. Those items rest on search summaries and are tagged [R].

---

## 1. Gemini API free tier, as of Oct 2026

### 1.1 Which models are free [C: https://ai.google.dev/gemini-api/docs/pricing]
The pricing page's Free Tier column says "Free of charge" for:
- `gemini-3.8-flash` and `gemini-3.5-flash-lite`.
- Live: `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`, `gemini-3.1-flash-live-preview`, `gemini-3.5-live-translate-preview`, `gemini-3.5-transcribe-live`.
- STT: `gemini-3.5-transcribe`.
- Native audio: `gemini-2.5-flash-native-audio-preview-12-2025`. Its access is limited to projects that used 2.5 models before [C: https://ai.google.dev/gemini-api/docs/models].
- TTS: `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.1-flash-tts-preview`, `gemini-2.5-flash-preview-tts`.
- Embeddings: `gemini-embedding-2-preview` (text input) and `gemini-embedding-001`.
- URL context: "Free of charge", billed as input tokens. It is supported on 3.8 Flash and 3.5 Flash-Lite [C: https://ai.google.dev/gemini-api/docs/url-context].

Not free:
- `gemini-2.5-pro-preview-tts` and every image-generation model ("Not available").
- Grounding with Google Search on `gemini-3.8-flash` and `gemini-3.5-flash-lite`. It is "Not available" on the free tier (3.5 Flash-Lite: can be tested in AI Studio only). Paid grounding has 5,000 free requests per month shared across Gemini 3+, then $14 per 1,000 [C: pricing page].
- The pricing page lists Search grounding as "Supported" for 3.8 Live. Whether that works on the free tier is UNVERIFIED. The Live tools page says Google Search works on Live models [C: https://ai.google.dev/gemini-api/docs/live-api/tools].
- Do not plan on web grounding. TEPHRA's "grounding" is its own evidence set.

### 1.2 RPM/RPD
- Google no longer publishes per-model free limits. The page says limits are per project (not per key), reset at midnight Pacific, and are viewable only at https://aistudio.google.com/rate-limit [C: https://ai.google.dev/gemini-api/docs/rate-limits].
- The "about 20 RPD for 3.8 Flash" and "500 RPD for Flash-Lite" figures are user-reported on one forum thread. No Google reply is on that thread [R: https://discuss.ai.google.dev/t/gemini-3-8-flash-free-tier-20-rpd-is-too-limited-for-practical-evaluation/180609].
- One third-party tracker's "~10 RPM / ~1,500 RPD" for "Gemini 3.x Flash" is explicitly indicative [R: https://klymentiev.com/blog/gemini-api-free-tier].
- Live, TTS and embedding free limits are UNVERIFIED. Someone must read the AI Studio rate-limit page once with the real key.
- Free-tier content "used to improve our products" [C: pricing page]. Dispatcher chat on a fictional airline is fine, but say so in the privacy note.

### 1.3 Live API and ephemeral tokens
- The Live API is a stateful WebSocket. Input is 16-bit PCM at 16 kHz, little-endian. Output is 16-bit PCM at 24 kHz [C: https://ai.google.dev/gemini-api/docs/live-api]. Models are `gemini-3.8-live` (stable) and `gemini-3.8-live-extended-thinking`.
- Free-tier Live is listed as "Free of charge" on the pricing page. The live-api page itself does not mention a free tier. A concurrency limit is not documented. An old table said 3 concurrent sessions for 2.5 Flash Live. Treat this as UNVERIFIED for 3.8.
- Session limits [C: https://ai.google.dev/gemini-api/docs/live-session]:
  - Audio-only sessions last up to 15 minutes without compression, and audio+video up to 2 minutes.
  - The connection ends after about 10 minutes, and the server sends a GoAway with `timeLeft`.
  - `contextWindowCompression` allows longer sessions. `sessionResumption` handles are valid for 2 hours.
- Ephemeral tokens [C: https://ai.google.dev/gemini-api/docs/ephemeral-tokens]:
  - They are in Preview, work only with the Live API, and require the `v1beta` endpoint.
  - The token goes in `access_token` on `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained` [C: https://ai.google.dev/gemini-api/docs/live-api/get-started-websocket].
  - Fields: `expireTime` (default 30 minutes), `newSessionExpireTime` (default 1 minute) and `uses` (use 1).
  - `liveConnectConstraints` locks the model and config. The system instruction can stay on the server.
  - The docs do not mention any free-tier restriction. Minting a token needs the real key, so mint it server-side behind TEPHRA's own auth.
- Live tool calling [C: https://ai.google.dev/gemini-api/docs/live-api/tools]:
  - The client must answer each `toolCall` with a `toolResponse`. There is no automatic handling.
  - `behavior: NON_BLOCKING` is available (not on 3.1 Flash Live).
  - Google Search can sit beside function declarations. URL context and code execution are not supported in Live.
- Transcripts: `serverContent.inputTranscription` and `outputTranscription` [C: get-started-websocket page].

### 1.4 Function calling and structured output
- Function calling modes are `auto`, `any`, `none` and `validated`. `allowed_tools` restricts the callable set. Parallel and compositional calls are supported, and Gemini 3 uses thought signatures (SDKs handle them) [C: https://ai.google.dev/gemini-api/docs/function-calling].
- Structured output with JSON Schema supports `enum`, `minimum`, `maximum`, `minItems`, `maxItems`, `anyOf`, `$ref` and `additionalProperties`. On Gemini 3 (preview) it can be combined with function calling, Search, URL context and code execution. The docs say to validate semantics in the app [C: https://ai.google.dev/gemini-api/docs/structured-output].
- ADK function tools: plain Python functions become `FunctionTool`. The docstring is the tool description, and `ToolContext` is injected. Return a dict with a `status` key [C: https://adk.dev/tools-custom/function-tools/]. `require_confirmation` and long-running tools exist. I did not read the confirmation page.

---

## 2. Browser speech on phones

- `SpeechRecognition` is still non-standard: caniuse marks it "partial" on Chrome Android 154 and iOS Safari 14.5–27.2, and Firefox has it disabled by default. The spec is unofficial [C: https://caniuse.com/speech-recognition].
- In Chrome, recognition is server-based. Audio goes to a web service and it does not work offline [C: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition].
- Chrome 139 added on-device recognition: `processLocally = true`, `SpeechRecognition.available()` and `install()` [R: https://developer.chrome.com/blog/new-in-chrome-139]. Language packs are about 60 MB each, and `install()` needs a user gesture [R: https://groups.google.com/a/chromium.org/g/blog-dev/c/VNOok2dbmHM/m/TQpe9shjCgAJ; the URL in my notes was blink-dev, UNVERIFIED]. The `processLocally` API is marked experimental on MDN.
- Whether iOS Safari's recognition is on-device is UNVERIFIED. Treat both browsers as "audio may leave the device" and say so in the UI.
- `speechSynthesis` is Baseline widely available. Gotchas [C: https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis]:
  - `speak()` should run inside a tap handler.
  - `getVoices()` loads asynchronously (use `voiceschanged`).
  - iOS voices and rate/pitch are inconsistent.
  - Network voices send the text to a remote service.
- CSP and headers:
  - `permissions-policy: camera=(), microphone=(), geolocation=()` is currently in `tephra/api/server.py` (line 115). Mic capture fails until that becomes `microphone=(self)`.
  - If the Live API is used from the browser, `connect-src` must add `wss://generativelanguage.googleapis.com`. If audio runs through an AudioWorklet, `worklet-src 'self'` (or `script-src 'self'`) is needed. Both are from general knowledge, UNVERIFIED against a source.
  - Web Speech needs no CSP change. It needs a secure context (HTTPS), which Cloud Run provides.

---

## 3. Grounded Q&A, refusal, validators, what-if

No single primary standard exists. These are patterns, with the literature behind them:
- The ALCE benchmark scores citation recall (is each statement entailed by its cited docs) and citation precision (is each citation needed). It reports a coverage-versus-citation-correctness trade-off [R: https://arxiv.org/pdf/2410.11217, https://arxiv.org/html/2509.21557v2]. Retrieval quality drives attribution quality.
- Google's guidance: "validate values in your application, since schema-valid output can still be semantically wrong" [C: structured-output page].
- Pattern: Gemini cites ids you supplied. Code then checks that every cited id exists, every number or ICAO code appears in an evidence item, and every quoted flight or level matches the tool results.

---

## 4. Gemini on satellite imagery

### 4.1 JMA Himawari Ash RGB quick guide [C: https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Ash_en.pdf, read via pdftotext]

Recipe in the current Ver. 1.0 guide:

| Channel | Bands | Range (K) | Gamma | Meaning |
|---|---|---|---|---|
| Red | B13−B15 (10.4−12.4 µm) | −3.0 to 7.5 | 1.0 | Cloud optical thickness; ash |
| Green | B11−B13 (8.6−10.4) / B11−B14 (8.6−11.2) | −1.6 to 4.9 / −5.9 to 5.1 | 1.2 / 0.85 | Cloud phase; SO2 |
| Blue | B13 inverted (10.4) | 243.6 to 303.2 | 1.0 | Cloud-top temperature |

- Colours: ash is red, scaled by concentration. SO2 is bright green. Mixed ash+SO2 is intermediate. Cold thick high cloud, thin cirrus and contrails have their own colour keys. Ice crystals over a plume can complicate reading (examples A–E in the guide).
- Stated limits:
  - Plume height and concentration cannot be estimated from the RGB alone.
  - Very thin or low-level plumes are hard to identify.
  - High cloud over a plume disturbs the signal.
  - Contrast depends strongly on viewing angle.
- This disagrees with the older 2015 slide in my search summary (red = B15−B13 range −4 to 2 K). Use the Ver. 1.0 numbers above.
- The JMA Dust RGB guide describes dust and ash as magenta or pinkish. Do not use Dust RGB for ash. See https://www.jma.go.jp/jma/jma-eng/satellite/VLab/QG/RGB_QG_Dust_en.pdf [R from search summary].
- Background: JMA MSC Technical Note No. 65 [R: https://www.data.jma.go.jp/mscweb/technotes/msctechrep65-1.pdf].

### 4.2 NASA GIBS
I fetched the full GIBS `epsg4326/best` capabilities (accessed 2026-10-11). The only Himawari layers are:
- `Himawari_AHI_Air_Mass`
- `Himawari_AHI_Band13_Clean_Infrared`
- `Himawari_AHI_Band3_Red_Visible_1km`

There is no Himawari Ash or Dust RGB layer, and no volcanic-ash identifier at all. NASA's blog describes a separate "Geostationary Ring Natural Color RGB" layer (3-hourly) [C: https://www.earthdata.nasa.gov/news/blog/new-geostationary-imagery-added-firms-worldview]. It says Worldview's Ash and Dust layers come from EUMETSAT satellites. So GIBS cannot supply an ash picture for Java, Halmahera or Kyushu. Use the Tokyo VAAC Ash RGB frames (per research/10) or compute the RGB from raw bands (per research/12). GIBS Band13 is only a corroborating grey IR picture.

### 4.3 Evaluations of multimodal LLMs
- I found no published Gemini evaluation on volcanic ash. Related work shows weak fine-grained grounding and small-object detection in remote sensing:
  - XLRS-Bench reports significant limits on large satellite images [R: search summary of https://arxiv.org/pdf/2411.18145v4; this URL is the search hit, not read in full, UNVERIFIED mapping].
  - "Charting New Territories" (GPT-4V on geospatial tasks) found strengths and failures [R: https://arxiv.org/pdf/2311.14656v1].
  - Noise and atmospheric effects are noted as barriers [R: same search].
  - Weather-specific MLLM work says off-the-shelf models handle raw multi-channel meteorological data poorly [R: https://www.arxiv.org/pdf/2404.15166; UNVERIFIED which paper].
- Gemini image API: boxes are `box_2d` as `[ymin, xmin, ymax, xmax]` normalised 0–1000, there is a `media_resolution` setting, and inline requests are capped at 20 MB [C: https://ai.google.dev/gemini-api/docs/image-understanding]. The page has no spatial-reasoning limitation section.
- JMA says the product cannot give height or concentration, so the model must not output them from the image.

---

## 5. Shift handover best practice

- FAA AC 121-32A "Dispatch Resource Management Training" is the DRM advisory circular. AC 120-101 is "Part 121 Air Carrier Operational Control", not DRM. I did not find either one's turnover text, UNVERIFIED [R: https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentid/22513].
- SKYbrary/Eurocontrol ATC handover [R: https://skybrary.aero/articles/handovertakeover-operational-atc-working-positionsresponses, via search summary]:
  - WEST checklist: Weather, Equipment, Situation, Traffic (pending traffic, future tasks, planned solutions).
  - Brief before the shift.
  - Keep distractions away.
  - Do not hand over while a critical task is open.
  - The outgoing person stays available for a few minutes.
  - The checklist does not remove responsibility from either party.
- I-PASS [R: Starmer et al., NEJM 2014;371:1803, via search summary]: Illness severity, Patient summary, Action list, Situation awareness and contingency, Synthesis by receiver. Reported effects: 23% fewer medical errors and 30% fewer preventable adverse events. The effect came from the full bundle, not the mnemonic alone, so I would not quote the percentages without the paper.
- NASA/JPL "Parke, handovers in MER surface ops" has a generic effective-handover checklist [R: https://hsi.arc.nasa.gov/publications/Parke_MER_SurfaceOps_Handovers_05.pdf]. I could not open it.

---

## 6. Mobile ops-UI, and how agent demos are judged

- Touch targets: Google says at least 48 dp with 8 dp spacing. Apple HIG says 44×44 pt. WCAG 2.2 AA's 24×24 floor exempts only inline text links, so citation chips need a padded hit area [R: https://support.google.com/accessibility/android/answer/7101858 and search summary].
- Thumb zone: the lower centre is easiest. Treat zone maps as heuristics, not measured data [R: search summary]. Put the composer and the Approve/Hold actions at the bottom.
- Streaming chat [R: https://thefrontkit.com/blogs/ai-chat-ui-best-practices]:
  - Buffer unfinished markdown.
  - Reserve space to avoid layout shift.
  - Keep Stop visible while streaming.
  - Attach citation chips only when their marker has streamed.
- Citation chips: small chip, +N for multiple sources, tap opens a bottom sheet with the exact passage, plus a Sources list [R: https://aiuxplayground.com/teardowns/chatgpt/citations]. These are third-party teardowns, not official guidance.
- Judges (see 08 for the criteria): no source says trace views win. Related support:
  - A 2026 agent-hackathon rubric scores "Running Code & Reliability" on repeatable end-to-end demos and graceful error handling.
  - An AI Tinkerers event gives bonus points for human-in-the-loop.
  - Past winners stress "auditability" (08's Outlook Business quote).
  - My inference: a visible timeline of tool calls with the human gate and a logged decision serves all three. This is inference, not a documented judging rule.

---

## 7. Licences and terms for sources used here

| Source | Terms | Public GitHub redistribution |
|---|---|---|
| JMA pages and imagery | PDL 1.0, compatible with CC BY 4.0. Attribution ("Source: Japan Meteorological Agency website" plus URL) required. State if edited and do not imply it is a JMA product. Third-party content, logos and symbols are excluded. Meteorological Service Act Art. 17(1) and Art. 23 restrictions apply [C: https://www.jma.go.jp/jma/en/copyright.html] | Yes with attribution, for small cropped samples. The page does not address bulk image redistribution specifically |
| JMA Quick Guide PDFs | Same site terms apply [C], so quote the recipe table and link. I would not copy the PDF into the repo | Link only |
| NASA GIBS | NASA data are open (per earlier research); I did not re-check the terms here, UNVERIFIED | Likely yes |
| Gemini API (free) | Content used to improve products [C: pricing page] | Never commit keys or tokens |
| MDN, caniuse, arXiv | Documentation or open papers; link, do not copy | n/a |

---

## Recommendation for TEPHRA

### A. "Ask TEPHRA" endpoint (grounded chat)
- Pipeline for `POST /api/ask`:
  1. Code builds an evidence pack from the current snapshot. Each item has an `id` (`E01`, `E02`, …), a `kind`, a `text` and a `fetched_utc`. Kinds: `sigmet`, `vaa`, `vona`, `metar`, `taf`, `wind`, `flight_plan`, `draft`, `cone`, `imagery_note`.
  2. One Gemini call, `gemini-3.5-flash-lite` (the 500/day budget; about 20/day on `gemini-3.8-flash`, user-reported, is too small to chat on). Use structured output.
  3. Code validates the result. On failure, re-ask once, then fall back to a canned "I can't answer that from the evidence" reply.
- Response schema:
  ```json
  {"answer": "string, max 600 chars",
   "claims": [{"text": "string", "source_ids": ["E03"], "kind": "fact|number|inference"}],
   "status": "answered|refused|needs_tool",
   "refusal_reason": "not_in_evidence|out_of_scope|needs_human",
   "follow_ups": ["string"]}
  ```
  Set `source_ids` `minItems: 1` for every claim, and enum-constrain `status`.
- Validator (pure Python, no model):
  1. Every `source_id` must exist in the pack.
  2. Extract every number (including FL values, headings and times) and every 4-letter ICAO or 3-letter code from `answer` and `claims`. Each must appear in the text of a cited item, or in a tool result for this turn. Normalise `FL200` = `200` = `20000 ft`, and allow ±0 tolerance.
  3. Any claim with `kind=inference` is stamped "TEPHRA inference" in the UI.
  4. If a check fails, set `status=refused` and show which claim failed. Log it.
- Refuse out-of-scope questions (legal, "is it safe to fly", forecasts). TEPHRA is not a forecaster (research/06, JMA Art. 17/23). Every answer carries "decision support, dispatcher decides".
- Prompt-injection note: evidence text (VAA free text) is untrusted. Pass it in a delimited data block and have code strip imperative lines.

### B. What-if via deterministic tools
- Give the model tools (ADK `FunctionTool`, or `tools` in the SDK with `allowed_tools`). Candidate tools: `flights_at_level(region, fl)`, `check_flight_vs_area(flight_id, area_id, fl_lo, fl_hi)`, `cone_with_level(fl_lo, fl_hi)`, `reroute_options(flight_id)`, `fuel_delta(flight_id, option)`, `draft_status(flight_id)`.
- Use `mode: validated` or `any` for what-if intents so the model must call a tool. Never let it compute geometry. Each tool returns a dict with `status`, results and an `evidence_id` (for example `T07`) that the answer cites as a source.
- Flow for "what if ash reaches FL200?": the tool runs the existing shapely logic with the level band changed and returns the flights affected, the minutes to boundary and the changed plan states. Gemini writes only the narrative. Cap at 4 tool calls per question.
- Cost-saving: a keyword router handles the five most common questions without any model call (status of a flight, why a plan was chosen, which flights are inside the area, last advisory time, who approved).

### C. Voice, in this order
1. Default to `SpeechRecognition` / `webkitSpeechRecognition` with `continuous=false`, `interimResults=true`. Check `processLocally` and `available()` where present, and prefer local if installed.
2. Feature-detect and hide the mic button when absent. Show the transcript in the composer for editing, never auto-send.
3. Replies use `speechSynthesis`, started from the tap that sent the question, with a speaker toggle off by default.
4. Optional stretch: Gemini Live (`gemini-3.8-live`) via an ephemeral token minted by `POST /api/live-token` (`uses:1`, `expireTime` about 10 minutes, `liveConnectConstraints` locking model and a server-side system instruction). It is free per the pricing page, but concurrency and RPD are UNVERIFIED, so it should be a demo flourish with the Web Speech path as the fallback. If used, answer `toolCall`s by calling the same `/api/ask` tools, and add `wss://generativelanguage.googleapis.com` to `connect-src`.
5. Change `permissions-policy` to `microphone=(self)` only on `/desk` (keep it `()` elsewhere). Show a visible "listening" state and a privacy line: "Speech may be processed by your browser vendor."

### D. "Satellite eyes" (Gemini on the imagery)
- Input: Tokyo VAAC Ash RGB frame crop, 3 frames (T−20, T−10, T), plus a legend image or a text legend: "red = ash, bright green = SO2, per JMA Ash RGB quick guide Ver. 1.0". Put the text prompt before the images, `media_resolution` high, and `thinking` low.
- Output schema (categorical only):
  ```json
  {"ash_visible": "yes|no|uncertain",
   "frames_with_ash": [0,1,2],
   "so2_visible": "yes|no|uncertain",
   "obscured_by_cloud": "yes|no|uncertain",
   "boxes": [{"label":"ash|so2","box_2d":[ymin,xmin,ymax,xmax],"frame":2}],
   "limits": "string"}
  ```
  Boxes are 0–1000. Code converts them to lat/lon and distances.
- Hard rules from JMA's stated limits: no height, no concentration, no new area outside the official polygon unless a box lies within the allowed widening, and a flag when `obscured_by_cloud` is not `no`. The image can only widen the official area, never shrink it.
- Evaluate before you claim it: run the 10 labelled cases from research/10 and report agreement (for example 10 images × 3 runs = 30 calls). State the number in the deck, even if low. Spend at most about 40 calls total.
- Show it as "Satellite check: consistent / unclear / not seen", with the crop, the box overlay and the JMA colour key. Do not use GIBS for ash (no layer exists).

### E. Shift handover brief
- One Flash-Lite call per handover, text in/text out, built from code-computed state. Schema (WEST plus I-PASS):
  ```json
  {"generated_utc": "", "shift_from": "", "shift_to": "",
   "severity": "calm|watch|active|critical",
   "weather_ash": {"official_areas": [], "latest_vaa_utc": "", "disagreements": [], "source_ids": []},
   "equipment_data": {"feeds_stale": [], "data_gaps": []},
   "situation": "",
   "traffic": [{"flight":"","plan":"","status":"draft|approved|held|rejected","reason":"","next_check_utc":""}],
   "actions_open": [{"owner":"","action":"","due_utc":""}],
   "contingencies": [{"if":"","then":""}],
   "decisions_made": [{"by":"","utc":"","what":""}],
   "receiver_ack": {"read_back_by": null, "utc": null}}
  ```
- Rules: every list item carries `source_ids` and goes through the section 3 validator. The receiver taps "Read back" (the I-PASS "synthesis by receiver" step), which writes `receiver_ack` and logs it. Show "outgoing dispatcher still reachable until HH:MM". Refuse to mark acknowledged while any draft is mid-approval (SKYbrary: do not hand over with a critical task open).
- Render the same JSON to a phone card and a printable one-page PDF/markdown.

### F. UI components (for `desk.html`)
- Ask sheet: expanding bottom sheet. Collapsed it is a 56 px bar "Ask TEPHRA" with a mic button. It sits above the existing queue and never covers the Approve/Hold buttons. Composer, mic, send/stop are at the bottom, each at least 48 px.
- Answer card: streamed text (buffer markdown, fixed-height container) and citation chips `[E03]`. The chip is visually small with a 44–48 px padded hit area and 8 px spacing. Tapping opens a modal sheet showing the evidence item verbatim, with source name, UTC time and a link. A "Sources (n)" row shows all of them. Claims with `kind=inference` get a dashed underline.
- Refusal card: a distinct neutral style, "Not in the evidence I have", listing what was checked.
- Agent timeline: a collapsible "How I answered" strip under each answer. It shows steps such as `evidence pack (14 items)` → `tool: check_flight_vs_area (38 ms)` → `validator: 6/6 numbers found` → `human gate`, with durations and pass/fail. This is the trace view judges can see in the 3-minute video. Keep it to one row per step.
- Approval gate: the existing Approve/Hold remains the only write path. Ask TEPHRA can open a draft but never approve it, and a chat answer never changes a plan state. Show "Proposed by AI, approved by <name> at <utc>".
- 8 AI feature presentation: use one persistent "AI" tray with 8 chips (Cone, Plans, ACARS, Ask, Satellite, Handover, Voice, Validator), each showing a status dot (idle, running, done, failed) and the free-tier budget left (for example "Flash-Lite 412/500 today"). Tapping a chip jumps to that feature's last output. Show a calls-used counter, because the free tier is a real constraint.
- Accessibility: aria-live polite for the streamed answer, a keyboard-reachable Send/Stop, and a text alternative for voice (every voice path has a typed path).

### G. Budget plan (free tier)
- Flash-Lite: Ask (cap 150/day via an in-app counter), handover (about 10/day), satellite check (about 40 total for the eval, then on demand). Flash (`gemini-3.8-flash`, about 20/day, UNVERIFIED): only the cone proposal and the final per-flight advisory.
- Cache the evidence-pack hash plus question hash for 5 minutes. On 429, show "AI budget used, showing deterministic answer" and fall back to the keyword router. Count per UTC date but remember quotas reset at midnight Pacific.
- Verify the real limits for all three models, Live and TTS in https://aistudio.google.com/rate-limit before building on them.

### H. Open items
- UNVERIFIED: free-tier RPM/RPD for 3.8 Flash and Flash-Lite, Live concurrency, and Live Search grounding on free.
- UNVERIFIED: whether iOS Safari recognition processes audio on-device.
- UNVERIFIED: AC 121-32A turnover text and the original ALCE paper's abstention behaviour.
- Update `tephra/web/THIRD_PARTY.md` with the JMA attribution wording above.

Files referenced (read-only): research/10-gemini-capability-and-architecture-check.md, research/15-dispatcher-reality.md, research/06-rules-terms-and-limits.md, research/08-competition-fit.md, docs/UI-DESIGN.md, tephra/api/server.py (permissions-policy at line 115). Scratch: <scratch>/r20/ (ash.txt, caps.xml).

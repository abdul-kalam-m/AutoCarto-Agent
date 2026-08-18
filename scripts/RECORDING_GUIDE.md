# Screen recording guide — AutoCarto-Agent demo for LinkedIn

All timings below were measured on this machine on 2026-08-11, not estimated.

---

## The one real problem to solve first

**Terminal text is unreadable on a phone.** Most LinkedIn video is watched on mobile, muted, one-handed. A default 12pt terminal at 1920×1080 becomes illegible when letterboxed into a phone feed. Everything below is arranged around fixing that.

Three things fix it:
1. **Terminal font at 20–24pt**, window narrowed to ~80 columns.
2. **Record a 1080×1080 square or 1080×1350 portrait region**, not the full desktop.
3. **Burn in text captions** for each beat — assume no sound.

---

## Measured timings (so you can plan the edit)

| Step | Real duration | In the video |
|---|---|---|
| `python -m venv` + pip upgrade | 11 s | keep, real time |
| `pip install -e ".[geo]"` (clean) | 60 s | **speed up 6–8×** → ~8 s |
| `autocarto demo` (cold / first run) | 5.3 s | — |
| `autocarto demo` (warm) | 1.8 s | keep, real time |
| `demo_for_video.py` (with pauses) | ~45 s | the spine of the video |
| `demo_for_video.py --fast` | ~22 s | if you need it tighter |
| ungated-vs-gated render | 6.8 s | keep — the wait *is* the point |

**Total raw footage: ~2.5 minutes → edits to 60–90 s.**

---

## Before you hit record

```bash
python scripts/demo_for_video.py --check
```

This verifies the geo extra and all three data snapshots, then **warms the imports**. Cold matplotlib/geopandas imports add ~4 seconds of dead air to the first run. Run `--check` first, then record **in that same terminal window**.

Also do:
- Close Slack/Teams/mail. Turn on Do Not Disturb.
- Clear the terminal, `cd` into the repo, and leave the prompt sitting there.
- Rehearse once with `--fast` so nothing surprises you.

---

## Shot list (60–90 seconds)

**Shot 1 — the hook (0:00–0:08)**
Open on the finished `ungated_vs_gated.png` full-screen, two maps side by side.
Caption: *"Same data. Same 530 neighborhoods. One of these maps is lying."*
Hold 3 s, then cut.

**Shot 2 — install (0:08–0:20)**
```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[geo]"
```
Speed 6–8×. Caption: *"Clean install — 71 seconds, sped up."*
This shot exists to prove it's a real package, not a notebook.

**Shot 3 — the problem (0:20–0:35)**
```bash
python scripts/demo_for_video.py
```
Let sections 1–2 play. The key frame is the class counts:
`[414, 86, 22, 5, 3]` → *"414 of 530 tracts land in ONE class."*
Caption: *"The default choice hides the entire pattern. The code ran fine."*

**Shot 4 — the fix (0:35–0:50)**
Section 2 output — the gate rejects and hands back exact numbers.
Caption: *"It doesn't just say no. It says: use these numbers."*
This is the single most important beat. Hold on `prescribed breaks` for a full 3 s.

**Shot 5 — the payoff (0:50–1:05)**
Section 3 renders; cut to the finished map pair.
Caption: *"Same data, corrected. [98 / 134 / 145 / 90 / 63]"*

**Shot 6 — real data (1:05–1:20)**
Section 4 — real Census income × real CDC asthma, 519 tracts.
Caption: *"On real data: higher income, lower asthma. It found a documented health pattern on its own."*

**Shot 7 — close (1:20–1:30)**
Terminal end card: *"The LLM proposes. The mathematics disposes."*
Caption: repo link + *"Presented at STDS 2026."*

---

## Recording tools (Windows)

**Easiest — Xbox Game Bar** (`Win + G`): built in, records the active window, no setup. Fine for this.

**Better — OBS Studio** (free): lets you set an exact 1080×1080 canvas, crop to the terminal, and record at 60fps. Worth the 15 minutes if you want it to look sharp.

**Editing:** Clipchamp (ships with Windows 11) handles the speed-ups and text overlays. CapCut is the alternative and is better at captions.

**Terminal setup:** Windows Terminal → Settings → Profiles → Appearance → font size 22, "One Half Dark" or "Campbell". A dark background reads better in a feed than a light one.

---

## Honesty guardrails for the caption text

The pipeline is real; the claims about it should stay inside what's shown.

- ✅ "Clean install in ~71 seconds" — measured
- ✅ "414 of 530 tracts collapse into one class" — printed live
- ✅ "Found a documented health pattern" — real ACS × CDC result
- ❌ Don't say "100% accurate" or "guarantees correct maps"
- ❌ Don't imply an LLM is calling the shots in this take — `demo_for_video.py` uses the deterministic client so the run is reproducible and offline. If you want a real-LLM run on camera, that's `autocarto run "..." --llm nvidia --data real` (~4–11 s, needs the API key and network — riskier live).
- ❌ Don't put "GVF" on screen. The naive map scores *higher* GVF than the corrected one; it's a genuinely interesting detail and a terrible one-line caption.

---

## If you want a second, shorter cut

A 30-second version that performs well: **Shot 1 → Shot 3 → Shot 4 → Shot 5.** Drop install and real-data. The problem-fix-payoff arc is the part people watch to the end.

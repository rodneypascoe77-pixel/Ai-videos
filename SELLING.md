# Faceless Video Engine — what you have to sell

This pipeline turns a topic into a finished, narrated, stock-footage video for
**pennies**. That makes it a sellable asset in several ways. Same engine, multiple
income streams.

## The product

`python -m longform.runner "your topic"` produces a self-contained deliverable in
`data/longform/<slug>/`:

| File | What it is |
|------|-----------|
| `video.mp4` | Finished narrated video (AI voice + stock footage + captions) |
| `thumbnail.png` | 1280×720 YouTube thumbnail |
| `title.txt` | Optimised title |
| `description.txt` | Description + tags |
| `script.json` | Full editable script (so a buyer can tweak/re-voice) |

Cost per video: **~$0.01–0.05** (Claude script only; voice + footage + assembly are free).

## Ways to monetise it

1. **Sell finished videos** — faceless creators and small businesses pay **$20–100**
   per video they don't want to make. Your cost is cents. Run `make_batch(n)` to fill
   an order.
2. **Run your own channels** — stock several niche channels; ad + sponsor revenue
   compounds as they grow. Cheap enough to run many in parallel.
3. **Channel-management retainer** — manage a brand's faceless channel for a
   **monthly fee** ($300–1,000); the engine does the production.
4. **Sell scripts / packages** — some buyers just want the `script.json` + thumbnail.
5. **Affiliate / lead-gen** — make videos around products you're an affiliate for;
   commissions beat ad RPM by orders of magnitude.

## Batch production (fulfilling an order / stocking a channel)

```python
from longform.runner import make_batch
make_batch(10, niche="unsolved historical mysteries")
```

## Knobs (in `.env`)

- `LONGFORM_NICHE` — default topic area
- `LONGFORM_VOICE` — any edge-tts voice (e.g. `en-US-GuyNeural`, `en-GB-RyanNeural`)
- `LONGFORM_SEGMENTS` — length (more segments = longer video = higher RPM)
- `PEXELS_API_KEY` — free stock footage (without it, falls back to caption slides)

## Margins, honestly

The expensive parts of video production (footage, voice, editing) are free or
near-free here. Your only real input is **time choosing niches and selling**. That
inverts the usual faceless-channel problem: instead of needing millions of views to
profit, you can profit on the **first sale** of a $0.05 video.

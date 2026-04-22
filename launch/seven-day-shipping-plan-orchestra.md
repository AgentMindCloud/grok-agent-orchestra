# Seven-day shipping plan — Grok Agent Orchestra

A senior solo-dev playbook for the week. Each day is one focused
block, one artefact out the door, one measurable signal back in. No
busywork; every step ships or discards.

---

## Day 1 — CI green + PyPI

**Goal:** every subsequent day can say "pip install grok-agent-orchestra".

- [ ] Push to `main`; confirm `.github/workflows/ci.yml` passes all
      four jobs (lint, test, schema-check, build).
- [ ] Tag `v0.1.0` and watch the `release` job publish to PyPI via
      trusted publishing (already wired).
- [ ] `pip install grok-agent-orchestra` from a clean venv; run
      `grok-orchestra --help`; confirm the banner renders.
- [ ] Open a release on GitHub with the CHANGELOG entry pasted in.
- [ ] Silent day — no announcement yet.

Measurable signal: PyPI download page live; the tag works.

## Day 2 — record the magic-moment GIF

**Goal:** 8-12 seconds that earn a stranger's attention.

The GIF is the single most important marketing artefact. It shows
the DebateTUI mid-run with the cyan→violet banner, a coloured role
divider, streaming tokens, and Lucas's green approval panel landing
at the end. Nothing else matters as much.

```bash
# 1. Start an OBS recording of a 1280x720 region covering a full-screen
#    terminal. Use truecolour; bump font to 18pt for legibility.
#
# 2. In the terminal, record a run:
PYTHONPATH=... grok-orchestra run \
  grok_orchestra/templates/orchestra-simulated-truthseeker.yaml --dry-run

# 3. Stop recording after Lucas's panel renders. Export as MP4 (not
#    MKV) to keep ffmpeg's job simple.
#
# 4. Convert to a palette-optimised GIF:
ffmpeg -i raw.mp4 -vf "fps=15,scale=900:-1:flags=lanczos,palettegen" palette.png
ffmpeg -i raw.mp4 -i palette.png -lavfi "fps=15,scale=900:-1:flags=lanczos [x]; [x][1:v] paletteuse" \
  docs/assets/orchestra-debate.gif

# 5. Sanity-check size — target ≤ 8 MB for Twitter, ≤ 15 MB as
#    fallback. If too big: drop fps to 12 or scale to 800:-1.
```

Commit the GIF to `docs/assets/orchestra-debate.gif`. Reference it
from the README hero block.

Measurable signal: GIF renders in the GitHub README preview, ≤ 8 MB.

## Day 3 — soft-launch X thread

**Goal:** first 100 eyeballs from people who care about Grok.

- [ ] Post `launch/x-thread-orchestra.md` as a single thread
      (tweet 1 with GIF).
- [ ] Pin the thread to the profile.
- [ ] Quote-retweet Bridge's thread from the same account.
- [ ] Reply once to each early quoted-reply with a specific follow-up
      (no "thanks!" — add signal).
- [ ] Do not boost paid. Community-first.

Measurable signal: thread hits ≥ 10 quoted-replies or ≥ 50 bookmarks
by end of day. If it undershoots, hold a debrief (next day) before
spending outreach budget.

## Day 4 — DM 20 Grok power-users

**Goal:** convert 2-3 of them into first-run screenshots we can
quote on Day 7.

- [ ] Build a shortlist of 20 people who either (a) posted about
      Grok 4.20 on X this week or (b) star-contributed to any
      Grok-adjacent repo.
- [ ] Send each a personal DM with a 30-second screen recording of
      `grok-orchestra combined --dry-run` on their own use-case (do
      the homework — name their use-case in sentence one).
- [ ] No mass-send. If you can't write a specific first sentence,
      drop the recipient.

Measurable signal: at least 5 DMs replied to; at least 2 users
install + run on their own spec.

## Day 5 — xAI email + newsletter outreach

**Goal:** make Orchestra known to the people who matter inside xAI
and in the Grok-adjacent press.

- [ ] Send `launch/email-xai-combined.md` to sales@x.ai (CC
      developers@x.ai). Reuse the thread link in the signature.
- [ ] Identify 5 relevant newsletters or podcasts. Send a 120-word
      pitch to each with the GIF attached + install one-liner +
      "happy to do a 15-minute live demo".
- [ ] Publish the GIF as an X post in its own right (not a reply
      to Day 3) for people who missed the thread.

Measurable signal: at least 1 newsletter reply; at least 1 xAI DM
or email reply within 72 hours.

## Day 6 — tutorial post

**Goal:** an artefact that keeps working long after the launch
buzz dies.

- [ ] Write a tutorial: "Build your first Grok agent in 60 seconds
      with Orchestra". End-to-end, with screenshots, from `pip
      install` through `grok-orchestra init` + `--dry-run` + reading
      the Lucas verdict.
- [ ] Cross-post: X (as a long-form thread or a link post) + dev.to
      (as a canonical article). Use the same hero GIF.
- [ ] Link the tutorial from the README's "Quick Start" section.

Measurable signal: tutorial gets ≥ 500 views on dev.to or ≥ 20
bookmarks on X within 24 hours.

## Day 7 — recap + metrics

**Goal:** a self-contained post that tells a stranger "this launched
this week, here's what happened" so the work compounds.

- [ ] Collect screenshots from Day 4's first users (with permission).
- [ ] Pull numbers: PyPI downloads, GitHub stars, thread
      impressions, notable replies.
- [ ] Post a recap thread (7 tweets):
      1. "7 days ago we shipped Grok Agent Orchestra. Here's what
         happened."
      2. One screenshot of a first-user spec + its Lucas approval.
      3. Download + star counts.
      4. The single best piece of feedback we got (quote the user
         with permission; paraphrase otherwise).
      5. What we shipped in response to feedback (name a commit).
      6. What's next — one pointer to a v0.2.0 feature on the
         roadmap.
      7. CTA: "`pip install grok-agent-orchestra`" + repo link.
- [ ] File a retrospective in `launch/` (keep it; ship the next
      launch from the same playbook).

Measurable signal: recap hits ≥ 50 bookmarks; at least 1 new
contributor PR opened in the next 72 hours.

---

## Guardrails for the whole week

- **Never post unverified numbers.** If PyPI is lagging, say so.
- **Never DM the same person twice** in week 1 unless they replied.
- **Cut any day that misses its signal by >50%.** Rolling a bad day
  into the next one is how solo launches die. Ship less, ship
  better.
- **Keep `safety.lucas_veto_enabled: true` in every demo spec.** The
  one time you post a draft that shouldn't have shipped will undo
  every other tweet this week.

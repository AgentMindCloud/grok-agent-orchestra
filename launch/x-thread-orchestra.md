# Launch thread — Grok Agent Orchestra

10 tweets, written to be pasted. Uses `·` and `→` instead of emoji
where possible so the thread reads clean on both dark + light mode.
Character counts are targets, not ceilings — trim if X re-counts.

---

## Tweet 1 — hook + GIF cue (≤ 240 chars)

> Watch 4 Grok agents debate a post live, catch the unsafe one, and
> ship the safe one — in one YAML.
>
> Grok Agent Orchestra: the missing multi-agent layer for Grok 4.20
> on X. Apache-2.0. ↓
>
> [attach orchestra-debate.gif — ~8s screen capture of the DebateTUI]

## Tweet 2 — how a debate actually looks

> Grok plans. Harper researches (web + x search). Benjamin checks
> the logic. Lucas hunts flaws.
>
> You see every system prompt. Every tool call. Every disagreement
> — resolved, not papered over.
>
> No black boxes. No "somehow the agents talked".

## Tweet 3 — the synthesis moment

> After the debate, Grok synthesises:
>
>   resolved: Harper vs Lucas on phrasing
>   → chose balanced framing
>   → because evidence-weight was even
>
> That one line is why the output is shippable. The debate isn't
> noise — it's the receipt.

## Tweet 4 — the TUI

> Live Rich TUI the whole time:
> · reasoning-token gauge (left)
> · streamed debate (right)
> · tool-calls footer
> · role divider with colour per speaker
>
> Exquisite. Zero flicker. Works in any terminal.

## Tweet 5 — Lucas veto moment (the headline safety feature)

> Before anything ships, Lucas (contrarian) runs a final veto at
> high reasoning effort on grok-4.20-0309.
>
> Strict JSON verdict: {safe, confidence, reasons, alternative_post}.
>
> Low confidence? Downgraded to unsafe. Malformed? Fails closed.
> Exit code 4 when denied.

## Tweet 6 — two modes, one YAML

> Native: grok-4.20-multi-agent-0309, 4 or 16 agents.
> Simulated: visible Grok/Harper/Benjamin/Lucas on grok-4.20-0309.
>
> Same YAML. `mode: auto` picks. `--dry-run` previews without
> spending tokens.

## Tweet 7 — combined with Grok Build Bridge

> The flex: one YAML that
>
> 1. has Bridge generate a Python module
> 2. runs an Orchestra debate over the generated code
> 3. Lucas vetoes the synthesis
> 4. ships the review to X
>
> `grok-orchestra combined trendseeker.yaml`

## Tweet 8 — templates

> 10 certified starter templates cover every pattern:
>
> native-4 · native-16 · simulated-truthseeker · hierarchical-research
> · dynamic-spawn · debate-loop · parallel-tools · recovery
> · combined-trendseeker · combined-coder-critic
>
> `grok-orchestra templates` to browse.

## Tweet 9 — install + repo

> `pip install grok-agent-orchestra`
> `grok-orchestra init orchestra-native-4 --out my-spec.yaml`
> `grok-orchestra run my-spec.yaml --dry-run`
>
> Full docs + schema + VS Code IntelliSense in the repo.
> github.com/agentmindcloud/grok-agent-orchestra

## Tweet 10 — CTA + handles + alt hooks

> Built by the community in Apache-2.0, 100% additive to official
> xai-sdk + grok-4.20-multi-agent-0309.
>
> Would love your feedback, xAI crew.
>
> @xai @grok @elonmusk
>
> ---
>
> alt hook #1: "Grok 4.20 + multi-agent + X-ready safety veto. One YAML."
> alt hook #2: "We taught 4 Grok agents to disagree safely. Apache-2.0."
> alt hook #3: "Every X post you've seen from Orchestra passed a Lucas veto."

---

## Notes for posting

- The headline GIF should be 8-12 seconds, ≤ 15 MB, showing a
  `grok-orchestra run --dry-run` on `basic-simulated.yaml` from
  start (banner) to the green approval panel. See
  `launch/seven-day-shipping-plan-orchestra.md` Day 2 for exact
  OBS + ffmpeg commands.
- Post the thread as a single reply chain, not as comment-replies.
- Quote-retweet Bridge's launch thread from the same account if
  Bridge shipped first.
- Pin the thread to the profile for 7 days.

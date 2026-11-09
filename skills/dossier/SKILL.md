---
name: dossier
description: Build, read, refresh and diff sourced briefs on an organisation or a professional contact. Use before a meeting, a sales call, an interview or a partnership conversation, and before re-using a brief that may be stale.
---

# Dossier

A dossier is a living file keyed to one entity, not a one-shot search. Every claim carries a source URL, a publication date and a retrieval date. Contradictions are printed as contested, never resolved silently.

## When to use it

- The user is about to meet, call, interview or evaluate an organisation or a person in a professional capacity.
- The user asks what is known about a company, or what has changed since last time.
- A brief already exists and may be stale, ask for the diff before trusting it.

Do **not** use it on a private individual with no professional context, or to look up anything in the sensitive categories below.

## The five calls

| Call | Use |
|---|---|
| `dossier_build` | First look. Pass `domain=` whenever you know it, it pins the entity. Pass `purpose=` and `context=` so the brief is framed for the meeting. |
| `dossier_show` | Read what is already stored, without touching the network. |
| `dossier_diff` | What changed between the last two snapshots. This is the pre-meeting question. |
| `dossier_refresh` | Re-fetch and snapshot, then report the diff. |
| `dossier_forget` | Delete everything about the entity. Requires `confirm=true`. |

Slash equivalents: `/dossier <name>`, `/dossier show|diff|refresh|forget <name>`.

## Frame it for the meeting

Ask, or infer from what the user said, what they are preparing for, and pass it:

- `context="interview"` for a job interview: team, role, how success is measured.
- `context="sales"` for a sales call: current spend, sign-off, urgency.
- `context="partnership"` for a partnership talk: the gap they cannot fill, the approver, the pilot.
- `context="diligence"` for due diligence: disagreeing sources, concentration, what stopped being said.
- `context="supplier"` for a supplier review: delivery exposure, who runs it, what changed.

Also pass `purpose=` in the user's own words ("interview for the platform role on Thursday"). It is printed on the brief, so it is worth getting right. If you pass only a purpose, the context is inferred from the words. A person dossier requires a purpose and defaults to `interview`.

## Rules that matter

1. **Ambiguity is a stop, not a guess.** If `dossier_build` returns `status: ambiguous`, show the candidate list and ask which one. Never pick the first.
2. **Do not paraphrase a claim past its evidence.** Quote the value and its date. If a claim is `contested`, present both sides; do not choose.
3. **A gap is a finding.** If a section is empty, say so, "no supported claim" is more useful than a plausible sentence.
4. **State the freshness.** Every brief has a snapshot time. Say it when you present the brief.
5. **Refuse the sensitive categories.** Health, religion, sexual orientation, political affiliation, ethnicity, trade-union membership, home address, family, precise location. If the user asks for them, decline and say why, the schema cannot store them anyway.

## Presenting a brief

Lead with the one line, then the three questions. That is the chat card. Offer the full brief path for the two-page document. When you report a refresh, report only what changed.

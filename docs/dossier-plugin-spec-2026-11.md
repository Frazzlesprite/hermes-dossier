<!-- Canonical copy: C:\Backpack\The-Library\documents\dossier-plugin-spec-2026-11.md
     This is a working copy for the repository. Edit the canonical copy, not this one. -->

# Dossier: Hermes plugin specification and handover

**Status:** build specification, v1
**Written:** 2026-11-08 (Australia Eastern, UTC+11)
**Plugin id:** `dossier`
**One line:** *Everything you should know before you walk in, sourced and dated.*

---

## 1. What it is

Dossier builds and maintains a two-page brief on a person or an organisation: what they do, who runs them, what changed recently, what contradicts itself, and three questions worth asking. Every claim carries a source and a date. The file persists, so the second look tells you **what changed since the first**.

It is not a search wrapper and not a one-shot research report. It is a living file keyed to an entity, refreshed before the meeting it is for.

---

## 2. Handover brief

### 2.1 State at handover

| Item | State |
|---|---|
| Specification | This document |
| Repository | **Does not exist yet.** Public, MIT, suggested `hermes-dossier` |
| Code | None |
| Catalog PR | Not opened |
| Demo | Not recorded |
| Deadline | **2026-11-12 09:00 AEDT** (2026-11-11 17:00 EST) |

### 2.2 Sequencing decision: read this first

The owner is building **Imprint** for the same deadline. Dossier is a second idea, and the honest assessment is that two full builds in three and a half days will produce two mediocre entries.

Two permitted paths:

- **Path A (recommended): post-hackathon.** Build Dossier properly after 12 November. Use this spec as-is.
- **Path B: a deliberately small second entry.** Only if Imprint's ledger and canon checker are green and its catalog PR is open by **Wednesday 11 November, 12:00 AEDT**. Build the `MVP-2` scope in section 5.2, not the full one. If that gate is missed, do not start.

Do not start Dossier before Imprint's PR is open. A second entry is worth less than a working first one.

### 2.3 First hour, in order

1. `hermes --version`; record it and set `requires_hermes` from it, not from this document.
2. Create the public MIT repository `hermes-dossier`, a **fresh** repo, not a fork of `hermes-agent`. The plugin lives here; the catalog entry is a separate one-file PR against a fork of the harness, pinning this repo and a full 40-character SHA.
3. Create the tree in Appendix A.
4. Prove the skeleton loads:

   ```
   hermes plugins doctor . --ci
   hermes plugins validate . --install-deps --ci
   ```

5. First commit: `chore: plugin skeleton passes doctor and validate`.
6. Read section 3 before writing a feature.

### 2.4 Non-negotiable invariants

- **No core overrides, no private imports.** Public hooks, `ctx.register_*`, `ctx.llm`, `ctx.plugin_db()` only.
- **Every hook accepts `**kwargs`.**
- **No unsourced sentence.** If a claim has no evidence row, it does not print. This is the product, not a nicety.
- **No sensitive-category inference.** See section 12. A dossier that infers health, religion, sexuality, politics or ethnicity is a liability and will be rejected.
- **No non-public personal data.** Organisations and professional public roles by default; no home addresses, personal numbers, or family details.
- **Network use is disclosed** in the README and the manifest, with the hosts named.
- **Rate limit and identify.** Respect `robots.txt`, send a descriptive User-Agent, one request per host per second.

### 2.5 Build order and acceptance

| Order | Milestone | Acceptance |
|---|---|---|
| 1 | Skeleton | `doctor --ci` and `validate --ci` pass |
| 2 | Entity resolution | A name resolves to one candidate, or asks the user to choose between two |
| 3 | Source adapters | Three adapters return normalised documents with dates |
| 4 | Claim extraction | Claims store a quote, a hash, a URL and a retrieval time |
| 5 | Verification | Confidence assigned; contradictions marked contested |
| 6 | Composition | A brief with every bullet citing evidence |
| 7 | Render | A4 HTML/PDF plus a chat card |
| 8 | Persistence + diff | Second run reports what changed since the first |
| 9 | Desktop | Dossier page with a refresh control |
| 10 | Ship | PR open and green, demo posted, form submitted |

### 2.6 Traps

- **Name collisions are the failure mode.** Two people share a name; the brief becomes about the wrong one. Require a disambiguator (employer, domain, registry id) and refuse to guess.
- **Search snippets lie.** Never treat a snippet as evidence; fetch the page and store a quote.
- **Dates decay.** A "recent news" section with no retrieval timestamp is a trap for the reader. Every claim carries `published_at` and `retrieved_at`.
- **The model will fill gaps.** The composition prompt must be constrained to the claim set, and the verifier must reject anything not in it.
- **Rate limits and paywalls.** Some sources will 403 or 429. Degrade to a note; never silently drop a source.

### 2.7 When blocked

| Blocker | Do this instead |
|---|---|
| No registry API key | Ship web and official-site adapters only; mark registry fields unverified |
| A source blocks fetching | Record "source unavailable" in the appendix; do not guess |
| Entity still ambiguous | Return the candidate list and stop. A wrong dossier is worse than none |
| Composition drifts | Cut the section rather than keep an unsourced sentence |

### 2.8 Definition of done

- [ ] `doctor --ci` and `validate --ci` pass
- [ ] A brief on a real company with every claim sourced and dated
- [ ] A second run produces a visible diff
- [ ] Contradictions render as contested with both sides
- [ ] No sensitive-category fields exist in the schema
- [ ] README opens with the disclosure and the permissible-use policy
- [ ] Catalog PR open with a full 40-character SHA
- [ ] Demo posted on X, under 90 seconds, showing it working
- [ ] Form submitted

---

## 3. Why this is a plugin and not a skill

A skill can run a search and write a summary. It cannot:

- resolve an entity once and key every future document to it;
- keep claim-level provenance with publication and retrieval dates;
- detect contradictions across sources and hold them as contested;
- diff a snapshot against the previous one and report only what changed;
- refresh on a schedule or before a calendar event;
- expose a Desktop page with the file's history.

The persistence and the diff are the product. A one-shot brief is a prompt; a file that updates itself is a system.

---

## 4. Judging alignment

| Criterion | How it scores |
|---|---|
| Usefulness | Pre-meeting research is real work people pay for. The diff is the part nobody else does. |
| Reliability | Entity resolution guardrails and unsourced-claim rejection are testable. The network is the weak point and degrades honestly. |
| Polish | A typeset two-page brief with a source appendix looks like a product. |
| Creativity | A dossier that tells you what changed, and refuses to speculate, is a distinct posture in a field of receipt plugins. |

---

## 5. Scope

### 5.1 Full scope

- Entity kinds: organisation and person (professional context only).
- Adapters: official site, web search, news, company registry, GitHub organisation.
- Claim model with confidence, contradiction and dates.
- Brief composition, A4 PDF/HTML, chat card, Desktop page.
- Snapshots and diff.
- Manual refresh, plus optional cron or calendar-triggered refresh.
- Watchlist with cadence.

### 5.2 MVP-2 scope (second-entry variant, two days)

- **Organisations only.**
- **Three adapters:** official site, web search, one registry.
- Brief card in chat plus a Desktop page. **No PDF.**
- **No diff, no cron, no watchlist.**
- One test fixture, one live run.

Everything else in this document is deferred.

---

## 6. Architecture

```
input ──► resolve.py ──► entity + disambiguator
              │
              ▼
         plan.py ──► research questions
              │
              ▼
      adapters/*.py ──► normalised documents (url, title, published_at, text)
              │
              ▼
        extract.py ──► claims + evidence quotes
              │
              ▼
        verify.py ──► confidence, dedupe, contradictions
              │
              ▼
       compose.py ──► brief sections, every bullet cited
              │
              ▼
        render.py ──► HTML/PDF, chat card
              │
              ▼
         store.py ──► snapshots + diff
```

Modules: `resolve.py`, `plan.py`, `adapters/`, `extract.py`, `verify.py`, `compose.py`, `render.py`, `store.py`, `tools.py`, `desktop/plugin.js`.

---

## 7. Manifest

```yaml
name: dossier
version: 0.1.0
manifest_version: 2
description: Sourced, dated, refreshable dossiers on people and organisations, with a what-changed diff.
license: MIT
homepage: https://github.com/<owner>/hermes-dossier
tags: [research, crm, due-diligence, briefing]
requires_hermes: "<record from hermes --version>"
config_schema:
  sources_per_brief: {type: int, default: 12}
  freshness_days: {type: int, default: 90}
  retention_days: {type: int, default: 90}
  allow_people: {type: bool, default: true, description: "Professional profiles only"}
provides_tools: [dossier_build, dossier_show, dossier_diff, dossier_refresh, dossier_forget]
provides_hooks:
  - pre_llm_call
```

Only declare what is registered.

---

## 8. Data model

```sql
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,            -- org | person
  canonical_name TEXT NOT NULL,
  aliases TEXT,                  -- JSON array
  domain TEXT,
  registry_id TEXT,              -- ABN, company number, CIK
  country TEXT,
  disambiguator TEXT,            -- employer, role, location
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL,
  predicate TEXT NOT NULL,       -- founded | employees | hq | ceo | funding | product | news
  value TEXT NOT NULL,
  confidence REAL NOT NULL,      -- 0..1
  status TEXT NOT NULL,          -- supported | contested | unconfirmed
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY,
  claim_id INTEGER NOT NULL,
  source_url TEXT NOT NULL,
  source_type TEXT NOT NULL,     -- registry | official | news | search | github
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  quote TEXT NOT NULL,           -- <= 500 chars
  quote_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL,
  taken_at TEXT NOT NULL,
  brief_html TEXT NOT NULL,
  claims_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
  entity_id INTEGER PRIMARY KEY,
  cadence TEXT,                  -- manual | daily | weekly
  calendar_hint TEXT,
  last_run TEXT
);
```

No column may hold a sensitive-category attribute. That is a design constraint, not a preference.

---

## 9. Research pipeline

1. **Resolve.** Query the registry and the web for the name. Build candidates with a disambiguator. If more than one survives, stop and ask.
2. **Plan.** Generate 8 to 16 concrete questions (what they sell, size, leadership, funding, recent changes, customers, competitors, risks).
3. **Fan out.** Run adapters in parallel, bounded by `sources_per_brief`. Normalise to `{url, title, published_at, retrieved_at, text}`.
4. **Extract.** Pull claims with a verbatim quote. Reject any claim without a quote.
5. **Verify.** Deduplicate by predicate and value. Assign confidence (section 10). Mark contradictions contested.
6. **Compose.** Sections, every bullet citing an evidence id. Refuse to write a bullet with no evidence.
7. **Snapshot and diff.** Store the brief and claim set; compare with the previous snapshot.
8. **Render.** HTML, PDF, chat card, Desktop page.

---

## 10. Confidence and contradiction rules

| Situation | Confidence | Status |
|---|---|---|
| Two independent primary sources agree (registry, official site, filing) | 0.95 | supported |
| One primary source | 0.80 | supported |
| One reputable secondary source | 0.60 | supported |
| Secondary sources disagree | 0.50 | contested: print both with dates |
| Only a snippet, or a source that could not be fetched | ≤ 0.40 | unconfirmed: appendix only |

A contested claim is never resolved silently. It prints as *"Source A says X (date); Source B says Y (date)"*. That is the most useful thing a dossier can do.

---

## 11. The brief

Two pages, A4:

1. **One line**, what they do, in plain language.
2. **Why they matter to you**, drawn from Hermes memory where relevant, never invented.
3. **Facts**, founded, size, HQ, leadership, funding, product.
4. **Recent**, last 90 days, each item dated.
5. **Contested or unconfirmed**, what the sources disagree about.
6. **Risks**, only claims that support a risk; no vibes.
7. **Three questions to ask**, derived from gaps and contradictions, not generic.
8. **Sources**, numbered, with publication and retrieval dates.

The chat card is the one-line plus the three questions. The Desktop page is the full brief with history.

---

## 12. Permissible use

This section exists because the obvious version of this plugin is a privacy problem.

**Allowed:** organisations; individuals in a professional public capacity, where the user supplies a work context (a meeting, a hiring process, a partnership).

**Not allowed:**

- sensitive-category inference or storage, health, religion, sexual orientation, political affiliation, ethnicity, trade union membership;
- non-public personal data, home address, personal phone, family members, precise location;
- allegations presented as fact without a court record;
- scraping behind a login or against a site's terms;
- building a dossier on a private individual with no professional context.

**Required:** a stated purpose at creation, a retention period, and `dossier_forget` that deletes the entity, claims, evidence and snapshots.

The README opens with this policy. The brief's footer repeats it in one line.

---

## 13. Output and surfaces

- **Chat card**: headline, three questions, a link to the full brief.
- **PDF/HTML**: two pages, source appendix.
- **Desktop page**: dossier list, full brief, history, refresh, forget.
- **Tools**: `dossier_build`, `dossier_show`, `dossier_diff`, `dossier_refresh`, `dossier_forget`.
- **Command**: `/dossier <name>`.

---

## 14. Tests

- Resolution: two same-name people, one employer; the resolver must ask, not guess.
- Extraction: a claim without a quote is rejected.
- Verification: two conflicting sources produce `contested`, not a winner.
- Composition: a bullet with no evidence id fails the build.
- Diff: a changed employee count appears in the diff; unchanged claims do not.
- Policy: a fixture containing a sensitive attribute is refused at extraction.
- Gates: `doctor --ci` and `validate --ci` clean.

---

## 15. Build plan

### 15.1 Full build (post-hackathon, five to six days)

| Day | Work |
|---|---|
| 1 | Skeleton, entity model, resolution with disambiguation |
| 2 | Three adapters, normalisation, extraction with quotes |
| 3 | Verification, confidence, contradictions |
| 4 | Composition, brief rendering, chat card |
| 5 | Snapshots, diff, Desktop page |
| 6 | Registry adapter, watchlist, hardening, tests |

### 15.2 MVP-2 (two days, only after the Imprint gate)

| Half-day | Work |
|---|---|
| 1 | Skeleton, org resolution, official-site adapter |
| 2 | Web search + registry adapters, extraction |
| 3 | Composition, chat card, Desktop page |
| 4 | One live run, one fixture, `validate --ci`, PR |

---

## 16. Demo shot list (90 seconds)

| Time | Shot |
|---|---|
| 0 to 8 | Type a company name. A progress line names each source as it lands. |
| 8 to 30 | The brief assembles: one line, facts, recent items, each with a date. |
| 30 to 45 | A contradiction appears: two sources disagree on headcount, both printed. |
| 45 to 60 | Three questions to ask, each derived from a gap. |
| 60 to 75 | Refresh: the diff shows one leadership change and nothing else. |
| 75 to 88 | Install line and the PR link. |

---

## 17. Catalog submission checklist

- Public MIT repo; README opens with the disclosure and the permissible-use policy.
- One `plugin-catalog/dossier.yaml`, full 40-character SHA.
- Network hosts named in the disclosure.
- `requires_hermes` truthful.
- Screenshots of the brief and the Desktop page.
- PR description: what it does, surfaces used, disclosure, and the contested-claim example.
- Demo on X tagging @NousResearch; both links through `form.typeform.com/to/FwJLvOln`.

---

## 18. Risks and fallbacks

| Risk | Mitigation | Fallback |
|---|---|---|
| Wrong person resolved | Require a disambiguator; ask on ambiguity | Return candidates and stop |
| Sources blocked or paywalled | Degrade to a note; never drop silently | Fewer sources, marked |
| Network flakiness in the demo | Pre-warm the cache; run against a saved source set | Show the diff instead of a live fetch |
| Model invents a claim | Composition constrained to claim ids; verifier rejects | Cut the section |
| Privacy objection | Permissible-use policy, no sensitive schema, forget command | Organisation-only mode |
| Deadline collision with Imprint | Sequencing gate in 2.2 | Post-hackathon build |

---

## Appendix A: repository layout

```
hermes-dossier/
├── plugin.yaml
├── __init__.py
├── schemas.py
├── tools.py
├── resolve.py
├── plan.py
├── adapters/
│   ├── base.py
│   ├── official.py
│   ├── search.py
│   ├── news.py
│   ├── registry.py
│   └── github.py
├── extract.py
├── verify.py
├── compose.py
├── render.py
├── store.py
├── db.py
├── desktop/plugin.js
├── skills/dossier/SKILL.md
├── tests/
│   ├── fixtures/company.json
│   ├── test_resolve.py
│   ├── test_verify.py
│   └── test_diff.py
├── README.md
└── LICENSE
```

## Appendix B: first five commits

1. `chore: plugin skeleton passes doctor and validate`
2. `feat: entity model and disambiguating resolver`
3. `feat: source adapters and claim extraction with quotes`
4. `feat: confidence, contradictions, and two-page brief`
5. `feat: snapshots, diff, and desktop page`

## Appendix C: the one sentence to keep

If a build decision is unclear, ask: **does this make the second look more useful than the first?** If not, it belongs to a search tool, not to Dossier.

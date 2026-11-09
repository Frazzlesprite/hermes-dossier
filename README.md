# Dossier

**Sourced, dated, refreshable briefs on organisations and people in a professional public capacity, and what changed since you last looked.**

Every sentence in a brief carries a source, a publication date and a retrieval date. If a claim has no evidence row, it does not print. A disagreement between sources is not resolved: it is printed as contested, with both sides and both dates.

---

## Disclosure: what this plugin does with your data

Dossier makes **outbound network requests** to read public pages. It sends a descriptive `User-Agent`, respects `robots.txt`, and makes at most one request per host per second.

Hosts it contacts:

| Host | Why |
|---|---|
| The entity's own domain (and pages it links to, e.g. `/about`) | The organisation describing itself |
| Whatever host your configured Hermes web-search backend returns | Finding candidate pages, which are then fetched in full |
| `api.github.com` and `github.com` | Public organisation profile and repositories |
| `www.sec.gov`, `data.sec.gov` | SEC EDGAR: the published ticker file, then filings per CIK (US, no key) |
| `abr.business.gov.au` | ABN Lookup (Australia, free GUID required) |
| `api.company-information.service.gov.uk` | Companies House (UK, free API key) |

It stores, in Hermes' per-plugin data directory (`plugin-data/dossier/`):

- the entity record, including the **purpose** you gave when you created it;
- claims, and for each claim the **verbatim quote**, source URL, publication date and retrieval date;
- every generated brief, as a snapshot, so the next run can diff against it.

It does **not** read credentials, `.env` files, browser profiles or other plugins' data. It has no telemetry and makes no analytics calls. If a model is available to the session, extracted claims are model-assisted but pass the same quote-verification gate as the deterministic extractor.

`/dossier forget <name>`, or the Delete button in the Desktop, removes the entity, its claims, its evidence and every snapshot.

---

## Permissible use

This section exists because the obvious version of this plugin is a privacy problem.

**Allowed:** organisations; individuals acting in a professional public capacity, where you supply a work context (a meeting, a hiring process, a partnership).

**Not allowed, and not implemented:**

- **no sensitive-category inference or storage:** health, religion, sexual orientation, political affiliation, ethnicity, trade-union membership. These are refused at extraction, before a claim can reach the database, and no column exists to hold them;
- **no non-public personal data:** home address, personal phone, family members, precise location;
- **no allegations presented as fact** without a court record;
- **no scraping behind a login** or against a site's terms;
- **no dossier on a private individual** with no professional context.

**Required:** a stated purpose at creation, a retention period, and `dossier_forget` that deletes everything.

The brief's footer repeats this in one line. The policy tests are in `tests/test_policy.py` and fail the build if a sensitive term becomes a predicate or a column.

---

## What it does

| Surface | What you get |
|---|---|
| `/dossier <name>` | Build or refresh a dossier, return a card |
| `/dossier show\|diff\|refresh\|forget\|watch <name>` | The other verbs |
| `dossier_build` / `dossier_show` / `dossier_diff` / `dossier_refresh` / `dossier_forget` / `dossier_watch` | The same six, as tools |
| Desktop → **Dossiers** | The list, the full brief, snapshot history, Refresh and Forget |
| Full brief | A4 **PDF** and HTML, two pages plus a numbered source appendix |
| Automation blueprint | A scheduled refresh users pick in `/blueprint`, no cron syntax |

A brief has: one line, why they matter to you (drawn from Hermes memory and labelled as memory), facts, recent items, contested or unconfirmed claims, risks, three questions to ask, and the sources.

Adapters: official site, web search, news, GitHub, and company registry (SEC EDGAR out of the box; ABN Lookup and Companies House when a credential is configured). A registry record is a primary source, so it carries the top confidence band.

Person dossiers get the same pipeline with `role` claims instead of `ceo`, and they **require a stated purpose:** the professional context. Without one the build is refused.

---

## Install

```bash
hermes plugins install owner/hermes-dossier    # from the catalog, once listed
```

Or for development, from a checkout:

```bash
# Windows
mklink /D "%LOCALAPPDATA%\hermes\plugins\dossier" "C:\Backpack\dossier-plugin"
```

Then enable it and restart the gateway so the dashboard routes mount:

```bash
hermes plugins enable dossier
```

The folder name must be `dossier`, because the Desktop loader requires the directory name to equal the plugin id.

---

## Configuration

Declared in `plugin.yaml`, editable in **Settings → Plugins → Dossier**:

| Key | Default | Meaning |
|---|---|---|
| `sources_per_brief` | `12` | Hard cap on documents fetched for one brief |
| `freshness_days` | `90` | Window for the Recent section |
| `retention_days` | `90` | How long a dossier is kept before it is reported stale |
| `allow_people` | `true` | Set false to refuse dossiers on individuals |
| `country` | `""` | Two-letter code for the registry adapter; empty asks every provider that has a credential |
| `registry_contact` | `""` | Contact email SEC requires in the User-Agent. EDGAR is skipped until this is set |
| `abn_lookup_guid` | secret | Free ABN Lookup GUID (Australia). Optional |
| `companies_house_api_key` | secret | Companies House API key (United Kingdom). Optional |
| `user_agent` | `Dossier/0.1 (+…)` | Identifies the plugin in requests |

There are no Python dependencies at all: the fetcher is `urllib`, and the PDF writer is 250 lines in `pdf.py`. Nothing to install, nothing to audit.

---

## How it is put together

```
name ──► resolve.py ──► one entity, or a question
             │
             ▼
         plan.py ──► queries and research questions
             │
             ▼
      adapters/*.py ──► normalised documents (url, title, published_at, text)
             │
             ▼
        extract.py ──► claims + verbatim quotes, policy-gated
             │
             ▼
        verify.py ──► confidence, dedupe, contested
             │
             ▼
       compose.py ──► sections, every bullet citing evidence
             │
             ▼
        render.py ──► A4 HTML + chat card
             │
             ▼
         store.py ──► snapshots + diff
```

Two deliberate design choices, both worth knowing before you change anything:

**Composition is deterministic.** `compose.py` applies templates to verified claims. It does not ask a model to write prose. That makes an unsourced sentence impossible by construction rather than by prompt discipline, and it means the same claim set always renders the same brief.

**Extraction is gated, not trusted.** The deterministic extractor captures the surrounding sentence as the quote. The optional model path returns a quote too, and both are rejected unless the quote is a verbatim substring of the fetched page text, at least 12 characters, inside the closed predicate set, and clear of every sensitive-category term. Rejections are counted and returned, never silently dropped.

**Ambiguity is stopped, not averaged.** Two same-name entities become a question, never a guess. And for a one-word name, where a homonym is likely, a third-party page is only allowed to contribute claims if it names the entity's own domain. The dropped sources are counted in the brief's notes, so the loss of coverage is visible rather than silent.

---

## Deviations from the v1 spec, and why

| Spec | Built | Why |
|---|---|---|
| `validate . --install-deps --ci` | `validate . --install-deps` (or `--json`) | `--ci` is a `doctor` flag, not a `validate` flag in Hermes 0.23.0. |
| `desktop/plugin.js` only | `desktop/plugin.js` **and** `dashboard/plugin_api.py` | The Desktop renderer can only reach Python over HTTP. Without a backend route the page has nothing to call. |
| `pre_llm_call` injects brief content | Injects a one-line pointer to an existing dossier only | Claim text in a system turn goes stale silently. The hook says a dossier exists, when it was taken, and offers the diff. |
| Calendar-triggered refresh | Watchlist cadence plus the automation blueprint | There is no calendar API to read. The cadence and `calendar_hint` are stored and shown; scheduling is the blueprint's cron job, which is the supported seam. |

---

## Development

```bash
python -m venv .venv
.venv\Scripts\pip install pytest pyyaml fastapi numpy
.venv\Scripts\python -m pytest tests
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

Two scripts do the unglamorous work of proving it outside the fixtures:

```bash
# one live brief against the real network, throwaway database
python scripts/live_check.py kalamari.club

# the installed plugin through Hermes' own storage, no model involved
set HERMES_HOME=%LOCALAPPDATA%\hermes
python scripts/harness_check.py kalamari.club https://kalamari.club

# the demo case offline: a contradiction, then a leadership change
python scripts/demo_contradiction.py

# the search and news adapters against the real Hermes web_search backend
python scripts/search_check.py "Kalamari" kalamari.club

# rebuild the demo videos (Pillow, numpy, imageio-ffmpeg; dev only)
python scripts/make_video.py
```

`scripts/search_check.py` imports one Hermes internal (`tools.web_tools.web_search_tool`) because there is no way to reach the search backend without a session context. That warning shows up in `hermes plugins validate`; the plugin itself uses `ctx.dispatch_tool` and nothing else.

## Demo

`docs/dossier-demo.mp4`: 72 seconds, built from a real run of `scripts/demo_contradiction.py`, so every figure on screen comes from the pipeline. A saved source set, no network, no model.

Three things that will save you an afternoon:

1. **The plugin root is a package.** Hermes loads it with `spec_from_file_location(..., submodule_search_locations=[plugin_dir])`, so internal imports are relative. A flat `import db` fails at load time, not at test time.
2. **Run pytest as `python -m pytest tests`.** `tests/pytest.ini` sets the rootdir to `tests` on purpose; without it the collector climbs out of the repo and tries to import the root `__init__.py` as a top-level module.
3. **Do not touch `ctx.llm` inside `register()`.** It is a property, and the validation probe's recording context does not stub properties, so `register()` raises and the `capability probe` check fails. Model access belongs in handlers.

---

## Licence

MIT. See `LICENSE`.

*Everything you should know before you walk in, sourced and dated.*

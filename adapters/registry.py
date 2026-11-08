"""Company-registry adapter: statutory records, where a free API exists.

Three providers, in order of what needs a key:

* **SEC EDGAR** (US) — no key, so it is the one that runs out of the box.
* **ABN Lookup** (AU) — free, needs a GUID registered by email.
* **Companies House** (UK) — free, needs an API key.

A provider with no credential is skipped with a note, never faked. Registry
records are *primary* sources, which is why they carry the top confidence in
`verify.py`: a filing is not an opinion.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
from typing import Any, Optional

from ..models import Document
from .base import Policy, fetch, json_load, now_iso

EDGAR_TICKERS = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_TTL_SECONDS = 7 * 24 * 3600

ABN_MATCH = "https://abr.business.gov.au/json/MatchingNames.aspx?name={q}&maxResults=5&guid={guid}"
ABN_DETAIL = "https://abr.business.gov.au/json/AbnDetails.aspx?abn={abn}&guid={guid}"
CH_SEARCH = "https://api.company-information.service.gov.uk/search/companies?q={q}&items_per_page=5"
CH_COMPANY = "https://api.company-information.service.gov.uk/company/{number}"

_CIK = re.compile(r"<cik>\s*(\d+)\s*</cik>")
_ticker_cache: dict[str, Any] = {"at": 0.0, "entries": {}}


def _ticker_cache_path() -> Optional[Any]:
    try:
        from plugins.plugin_storage import plugin_data_dir  # noqa: PLC0415

        return plugin_data_dir("dossier") / "edgar_tickers.json"
    except Exception:
        return None


def _load_tickers(policy: Optional[Policy] = None) -> dict[str, int]:
    """company name (casefolded) -> CIK, cached for a week.

    `www.sec.gov/cgi-bin/browse-edgar` is disallowed by the site's robots.txt,
    so the lookup uses the published ticker file instead — which is a bulk file
    meant for exactly this — and then the JSON submissions API per CIK.
    """
    now = time.time()
    if _ticker_cache["entries"] and now - _ticker_cache["at"] < EDGAR_TTL_SECONDS:
        return _ticker_cache["entries"]

    path = _ticker_cache_path()
    if path is not None and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if now - float(payload.get("at", 0)) < EDGAR_TTL_SECONDS:
                entries = {k: int(v) for k, v in payload.get("entries", {}).items()}
                if entries:
                    _ticker_cache.update({"at": float(payload["at"]), "entries": entries})
                    return entries
        except Exception:
            pass

    response = fetch(EDGAR_TICKERS, policy)
    payload = json_load(response.text) if response.text else None
    entries: dict[str, int] = {}
    if isinstance(payload, dict):
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            title = _quote(value.get("title")).casefold()
            cik = value.get("cik_str")
            if title and isinstance(cik, int):
                entries.setdefault(title, cik)
    if not entries:
        return {}

    _ticker_cache.update({"at": now, "entries": entries})
    if path is not None:
        try:
            path.write_text(json.dumps({"at": now, "entries": entries}), encoding="utf-8")
        except OSError:
            pass
    return entries


def _match_cik(name: str, entries: dict[str, int]) -> Optional[int]:
    wanted = _quote(name).casefold()
    if not wanted:
        return None
    if wanted in entries:
        return entries[wanted]
    starts = [(title, cik) for title, cik in entries.items() if title.startswith(wanted)]
    if starts:
        # "Apple Inc." beats "Apple Hospitality REIT, Inc." — the parent company
        # is the one with the shortest registered title.
        return min(starts, key=lambda pair: len(pair[0]))[1]
    contains = [cik for title, cik in entries.items() if wanted in title]
    if len(contains) == 1:
        return contains[0]
    return None



def _quote(text: str) -> str:
    return " ".join(str(text or "").split())


def _with_user_agent(policy: Optional[Policy], user_agent: str) -> Policy:
    base = policy or Policy()
    return Policy(
        user_agent=user_agent,
        timeout=base.timeout,
        max_bytes=base.max_bytes,
        respect_robots=base.respect_robots,
        min_interval=base.min_interval,
        extra_headers=dict(base.extra_headers),
    )


def _document(url: str, title: str, lines: list[str], note: str) -> Document:
    return Document(
        url=url,
        title=title,
        text=" ".join(line for line in lines if line).strip(),
        source_type="registry",
        retrieved_at=now_iso(),
        published_at=None,
        domain=urllib.parse.urlparse(url).hostname or "",
        note=note,
    )


# --------------------------------------------------------------------- EDGAR


def collect_edgar(name: str, policy: Optional[Policy] = None, *, contact: str = "") -> dict[str, Any]:
    if not contact:
        return {
            "documents": [],
            "notes": [
                "registry(EDGAR): SEC requires a declared contact in the User-Agent; "
                "set registry_contact (an email address) to enable US filings"
            ],
        }
    # SEC's edge rejects a User-Agent containing a URL, and requires a contact
    # email. The contact is the user's, not the plugin's: we never invent one.
    scoped = _with_user_agent(policy, f"Dossier/0.1 {contact}")
    entries = _load_tickers(scoped)
    if not entries:
        return {
            "documents": [],
            "notes": ["registry(EDGAR): the SEC ticker file was unavailable, so no CIK lookup was possible"],
        }

    cik_int = _match_cik(name, entries)
    if cik_int is None:
        return {"documents": [], "notes": [f"registry(EDGAR): no registrant matched {name!r}"]}

    cik = f"{cik_int:010d}"
    submissions = fetch(EDGAR_SUBMISSIONS.format(cik=cik), scoped)
    payload = json_load(submissions.text) if submissions.text else None
    if not isinstance(payload, dict):
        return {
            "documents": [],
            "notes": [f"registry(EDGAR): CIK {cik} found but submissions were unreadable — {submissions.error or 'no JSON'}"],
        }

    registrant = _quote(payload.get("name") or name)
    lines = [f"{registrant} is registered with the U.S. Securities and Exchange Commission under CIK {cik}."]

    sic = payload.get("sicDescription")
    if sic:
        lines.append(f"Its filings classify it under {sic}.")

    addresses = payload.get("addresses") or {}
    business = addresses.get("business") or {}
    city = _quote(business.get("city"))
    state = _quote(business.get("stateOrCountry"))
    if city:
        location = f"{city.title()}, {state}" if state else city.title()
        lines.append(f"Headquartered in {location}.")

    filings = (payload.get("filings") or {}).get("recent") or {}
    forms = filings.get("form") or []
    dates = filings.get("filingDate") or []
    annual = next(
        ((form, date) for form, date in zip(forms, dates) if form in ("10-K", "20-F", "40-F")),
        None,
    )
    chosen = annual or next(
        ((form, date) for form, date in zip(forms, dates) if form == "10-Q"), None
    )
    if chosen:
        lines.append(f"Filed its {chosen[0]} on {chosen[1]}.")

    doc = _document(
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
        f"{registrant} — SEC EDGAR",
        lines,
        "rendered from the public SEC EDGAR API",
    )
    return {"documents": [doc], "notes": []}


# ------------------------------------------------------------------ ABN (AU)


def _jsonp(text: str) -> Any:
    body = (text or "").strip()
    start = body.find("(")
    end = body.rfind(")")
    if start != -1 and end > start:
        body = body[start + 1 : end]
    return json_load(body)


def collect_abn(name: str, guid: str, policy: Optional[Policy] = None) -> dict[str, Any]:
    if not guid:
        return {"documents": [], "notes": ["registry(ABN): no ABN Lookup GUID configured; AU registry fields unverified"]}

    matched = fetch(ABN_MATCH.format(q=urllib.parse.quote(name), guid=guid), policy)
    payload = _jsonp(matched.text) if matched.text else None
    if not isinstance(payload, dict) or payload.get("Message"):
        return {"documents": [], "notes": [f"registry(ABN): lookup refused — {(payload or {}).get('Message') or matched.error or 'no response'}"]}

    names = payload.get("Names") or []
    if not names:
        return {"documents": [], "notes": [f"registry(ABN): no ABN matched {name!r}"]}

    entry = names[0]
    abn = str(entry.get("Abn") or "").replace(" ", "")
    detail = fetch(ABN_DETAIL.format(abn=urllib.parse.quote(abn), guid=guid), policy)
    record = _jsonp(detail.text) if detail.text else None
    if not isinstance(record, dict):
        record = entry

    entity_name = _quote(record.get("EntityName") or entry.get("Name") or name)
    formatted = " ".join(
        [abn[0:2], abn[2:5], abn[5:8], abn[8:]]
    ) if len(abn) == 11 else abn

    lines = [f"{entity_name} is registered with the Australian Business Register under ABN {formatted}."]
    state = _quote(record.get("AddressState") or record.get("State"))
    if state:
        lines.append(f"Located in {state.title()}.")
    status = _quote(record.get("AbnStatus") or entry.get("AbnStatus"))
    if status:
        lines.append(f"Its ABN status is {status}.")
    code = _quote(record.get("EntityTypeName"))
    if code:
        lines.append(f"Its registered entity type is {code}.")

    doc = _document(
        f"https://abr.business.gov.au/ABN/View?abn={abn}",
        f"{entity_name} — ABN Lookup",
        lines,
        "rendered from the public ABN Lookup service",
    )
    return {"documents": [doc], "notes": []}


# --------------------------------------------------------- Companies House UK


def _ch_policy(api_key: str, policy: Optional[Policy]) -> Policy:
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    base = policy or Policy()
    headers = dict(base.extra_headers)
    headers["Authorization"] = f"Basic {token}"
    return Policy(
        user_agent=base.user_agent,
        timeout=base.timeout,
        max_bytes=base.max_bytes,
        respect_robots=base.respect_robots,
        min_interval=base.min_interval,
        extra_headers=headers,
    )


def collect_companies_house(name: str, api_key: str, policy: Optional[Policy] = None) -> dict[str, Any]:
    if not api_key:
        return {"documents": [], "notes": ["registry(Companies House): no API key configured; UK registry fields unverified"]}

    scoped = _ch_policy(api_key, policy)
    search = fetch(CH_SEARCH.format(q=urllib.parse.quote(name)), scoped)
    payload = json_load(search.text) if search.text else None
    items = (payload or {}).get("items") or []
    if not items:
        return {"documents": [], "notes": [f"registry(Companies House): no company matched {name!r} — {search.error or 'no results'}"]}

    number = items[0].get("company_number")
    if not number:
        return {"documents": [], "notes": ["registry(Companies House): result had no company number"]}

    detail = fetch(CH_COMPANY.format(number=number), scoped)
    record = json_load(detail.text) if detail.text else None
    if not isinstance(record, dict):
        record = items[0]

    company = _quote(record.get("company_name") or name)
    lines = [f"{company} is registered with UK Companies House as company number {number}."]
    incorporated = _quote(record.get("date_of_creation"))
    if incorporated:
        lines.append(f"Incorporated in {incorporated[:4]}.")
    office = (record.get("registered_office_address") or {})
    town = _quote(office.get("locality") or office.get("postal_town"))
    if town:
        lines.append(f"Its registered office is located in {town.title()}.")
    status = _quote(record.get("company_status"))
    if status:
        lines.append(f"Its Companies House status is {status}.")
    sic = record.get("sic_codes") or []
    if sic:
        lines.append(f"Its registered activity code is {sic[0]}.")

    doc = _document(
        f"https://find-and-update.company-information.service.gov.uk/company/{number}",
        f"{company} — Companies House",
        lines,
        "rendered from the public Companies House API",
    )
    return {"documents": [doc], "notes": []}


def collect_registry(
    name: str,
    *,
    country: Optional[str] = None,
    policy: Optional[Policy] = None,
    abn_guid: str = "",
    companies_house_key: str = "",
    contact: str = "",
) -> dict[str, Any]:
    """Query every provider that has a credential, and say what was skipped."""
    documents: list[Document] = []
    notes: list[str] = []

    wanted = (country or "").upper()
    providers = []
    if wanted in ("", "US", "USA", "UNITED STATES"):
        providers.append(("edgar", lambda: collect_edgar(name, policy, contact=contact)))
    if wanted in ("", "AU", "AUS", "AUSTRALIA"):
        providers.append(("abn", lambda: collect_abn(name, abn_guid, policy)))
    if wanted in ("", "GB", "UK", "UNITED KINGDOM"):
        providers.append(("ch", lambda: collect_companies_house(name, companies_house_key, policy)))

    for _key, run in providers:
        try:
            result = run()
        except Exception as exc:  # a registry outage is a note, not a crash
            notes.append(f"registry: provider failed — {type(exc).__name__}: {exc}")
            continue
        documents.extend(result.get("documents") or [])
        notes.extend(result.get("notes") or [])

    return {"documents": documents, "notes": notes}

"""Government schemes data service.

Single ingestion boundary for official government-scheme data:

    configured GoI / Ministry endpoints  ->  validate/normalize  ->  government_schemes table

Sources (data.gov.in resource ids, API Setu keys, or plain official JSON
endpoints) are configured only in backend settings (.env) and are never sent
to clients as secrets. Nothing is fabricated, imported or labelled "live"
unless a configured official source actually responds with valid JSON. When a
source is unreachable or not configured, callers get an explicit status and
the stored (timestamped) catalog is served with honest freshness labels.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.government import GovernmentScheme, SchemeSyncLog
from app.utils.auth import generate_id


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------

def source_configured() -> bool:
    return bool(
        settings.GOV_SCHEMES_API_KEY
        and (settings.GOV_SCHEMES_SOURCE_URLS or settings.GOV_SCHEMES_RESOURCE_IDS)
    )


def _clean_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, (list, dict)):
        return None
    text = str(raw).strip()
    return text or None


def _parse_list(raw: Any) -> List[str]:
    """Return a clean list of strings from str / list / JSON input."""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        return parts
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.extend(_parse_list(item))
            elif isinstance(item, dict):
                for key in ("name", "title", "value"):
                    if item.get(key):
                        out.append(_clean_str(item.get(key)))
        return out
    return []


def _parse_date(raw: Any) -> Optional[str]:
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _is_national_state(raw: Optional[str]) -> bool:
    if not raw:
        return True
    low = raw.strip().lower()
    return low in ("", "all", "all india", "national", "nationwide", "central", "india")


def _infer_benefit_type(category: Optional[str], name: str) -> Optional[str]:
    text = f"{category or ''} {name}".lower()
    if "insurance" in text or "fasal bima" in text:
        return "insurance"
    if "pension" in text or "maan dhan" in text:
        return "pension"
    if "loan" in text or "credit" in text or "kcc" in text:
        return "loan"
    if "subsidy" in text or "subvention" in text:
        return "subsidy"
    if "income support" in text or "pm kisan" in text:
        return "income"
    return None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_scheme(rec: Dict[str, Any], source_name: str) -> Optional[Dict[str, Any]]:
    """Validate/normalize one raw official record. Returns None if unusable.

    Only the `name` is strictly required; a record also needs at least one of
    description/benefits/eligibility to be worth storing. All field extraction
    is alias-based so different official endpoints can feed the same pipeline.
    """
    name = _clean_str(
        rec.get("name")
        or rec.get("title")
        or rec.get("scheme_name")
        or rec.get("scheme_name_en")
        or rec.get("Name")
    )
    description = _clean_str(
        rec.get("description")
        or rec.get("overview")
        or rec.get("details")
        or rec.get("benefits_overview")
        or rec.get("Description")
    )
    benefits = _clean_str(
        rec.get("benefits")
        or rec.get("benefit")
        or rec.get("Benefits")
    )
    eligibility = _clean_str(
        rec.get("eligibility")
        or rec.get("eligibility_criteria")
        or rec.get("eligibility_criteria_details")
        or rec.get("Eligibility")
    )
    if not name:
        return None
    if not (description or benefits or eligibility):
        return None

    raw_state = _clean_str(rec.get("state") or rec.get("applies_to") or rec.get("State"))
    state = None if _is_national_state(raw_state) else raw_state
    category = _clean_str(rec.get("category") or rec.get("type") or rec.get("scheme_type") or rec.get("Category"))
    source_url = _clean_str(
        rec.get("source_url")
        or rec.get("website")
        or rec.get("scheme_url")
        or rec.get("url")
        or rec.get("official_url")
    )
    crop = _clean_str(rec.get("crop") or rec.get("crop_specific") or rec.get("Sector") or rec.get("sector"))

    return {
        "name": name,
        "description": description or benefits,
        "eligibility": eligibility,
        "benefits": benefits,
        "state": state,
        "crop": crop,
        "category": category,
        "application_deadline": _parse_date(
            rec.get("application_deadline")
            or rec.get("deadline")
            or rec.get("end_date")
            or rec.get("last_date")
        ),
        "documents_required": _parse_list(
            rec.get("documents_required") or rec.get("documents") or rec.get("required_documents")
        ) or None,
        "how_to_apply": _clean_str(
            rec.get("how_to_apply")
            or rec.get("application_process")
            or rec.get("How_to_Apply")
        ),
        "website": source_url,
        "department": _clean_str(
            rec.get("department")
            or rec.get("implementing_agency")
            or rec.get("ministry")
            or rec.get("Department")
            or rec.get("Ministry")
        ),
        "level": "state" if state else "central",
        "overview": description,
        "objectives": _clean_str(rec.get("objectives") or rec.get("aims") or rec.get("Objectives")),
        "application_process": _clean_str(rec.get("application_process") or rec.get("How_to_apply")),
        "contact_information": _clean_str(
            rec.get("contact_information")
            or rec.get("helpdesk")
            or rec.get("helpline")
            or rec.get("Contact")
        ),
        "source": source_name,
        "source_url": source_url,
        "start_date": _parse_date(rec.get("start_date") or rec.get("launch_date") or rec.get("Start_Date")),
        "faqs": rec.get("faqs")
        if isinstance(rec.get("faqs"), list)
        else None,
        "related_crops": _parse_list(rec.get("related_crops") or rec.get("crops") or rec.get("supported_crops")) or None,
        "eligible_farmer_types": _parse_list(
            rec.get("eligible_farmer_types")
            or rec.get("farmer_types")
            or rec.get("target_beneficiaries")
        ) or None,
        "land_category": _clean_str(rec.get("land_category") or rec.get("land_holding")),
        "income_category": _clean_str(rec.get("income_category") or rec.get("annual_income_limit")),
        "benefit_type": _infer_benefit_type(category, name),
        "category": category,
        "last_verified_at": datetime.utcnow(),
    }


def _natural_key(row: Dict[str, Any]):
    if row.get("scheme_id"):
        return ("id", row["scheme_id"])
    return ("name", row["name"])


def upsert_schemes(db: Session, rows: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    """Insert new official schemes; update stored ones on the natural key.

    Returns (count stored, list of stored scheme_ids). If the official record
    carries its own canonical scheme_id it is honoured; otherwise a new
    FA-SCH-###### id is minted for public reference.
    """
    stored = 0
    stored_keys: List[str] = []
    next_id: Optional[str] = None
    for row in rows:
        if row.get("scheme_id"):
            existing = db.query(GovernmentScheme).filter(
                GovernmentScheme.scheme_id == row["scheme_id"]
            ).first()
        else:
            existing = db.query(GovernmentScheme).filter(
                GovernmentScheme.source == row["source"],
                func.lower(GovernmentScheme.name) == row["name"].lower(),
            ).first()
        if existing:
            changed = False
            for field in (
                "name", "description", "eligibility", "benefits", "state", "crop",
                "category", "application_deadline", "documents_required", "how_to_apply",
                "website", "department", "level", "overview", "objectives",
                "application_process", "contact_information", "source", "source_url",
                "start_date", "faqs", "related_crops", "eligible_farmer_types",
                "land_category", "income_category", "benefit_type",
            ):
                if row.get(field) is not None and getattr(existing, field) != row.get(field):
                    setattr(existing, field, row.get(field))
                    changed = True
            if changed:
                existing.last_verified_at = row["last_verified_at"]
                stored += 1
            stored_keys.append(existing.scheme_id)
            continue
        if "scheme_id" in row and row["scheme_id"]:
            scheme_id = row["scheme_id"]
        else:
            if next_id is None:
                next_id = generate_id("FA-SCH", db, GovernmentScheme)
            scheme_id = next_id
            try:
                prefix, num = next_id.rsplit("-", 1)
                next_id = f"{prefix}-{str(int(num) + 1).zfill(6)}"
            except ValueError:
                next_id = generate_id("FA-SCH", db, GovernmentScheme)
        entry = GovernmentScheme(
            scheme_id=scheme_id,
            status="active",
            last_verified_at=row["last_verified_at"],
            **{k: row.get(k) for k in (
                "name", "description", "eligibility", "benefits", "state", "crop",
                "category", "application_deadline", "documents_required", "how_to_apply",
                "website", "department", "level", "overview", "objectives",
                "application_process", "contact_information", "source", "source_url",
                "start_date", "faqs", "related_crops", "eligible_farmer_types",
                "land_category", "income_category", "benefit_type",
            )},
        )
        db.add(entry)
        stored += 1
        stored_keys.append(scheme_id)
    db.commit()
    return stored, stored_keys


# ---------------------------------------------------------------------------
# Sync from configured official sources
# ---------------------------------------------------------------------------

def _record_sync(
    db: Session,
    status: str,
    trigger: str,
    message: str,
    fetched: int = 0,
    stored: int = 0,
    source: Optional[str] = None,
) -> SchemeSyncLog:
    sync = SchemeSyncLog(
        status=status,
        trigger=trigger,
        source=source or settings.GOV_SCHEMES_SOURCE_NAME,
        records_fetched=fetched,
        records_stored=stored,
        message=message[:500] if message else None,
        synced_at=datetime.utcnow(),
    )
    db.add(sync)
    db.commit()
    return sync


def _configured_sources() -> List[Dict[str, str]]:
    sources: List[Dict[str, str]] = []
    for resource_id in settings.GOV_SCHEMES_RESOURCE_IDS:
        if resource_id:
            sources.append({
                "label": resource_id,
                "url": f"{settings.GOV_SCHEMES_SOURCE_BASE.rstrip('/')}/{resource_id}",
                "type": "data_gov_in",
            })
    for url in settings.GOV_SCHEMES_SOURCE_URLS:
        if url:
            sources.append({"label": url, "url": url, "type": "json"})
    return sources


def _fetch_records(url: str, source_type: str) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"format": "json"}
    if settings.GOV_SCHEMES_API_KEY:
        params["api-key"] = settings.GOV_SCHEMES_API_KEY
    with httpx.Client(timeout=25) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    records = payload.get("records")
    if not isinstance(records, list):
        records = payload.get("data")
    if not isinstance(records, list):
        for key in ("schemes", "results", "result", "items", "content"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
    return records if isinstance(records, list) else []


def sync_from_sources(
    db: Session,
    trigger: str = "manual",
    force: bool = False,
    limit: int = 500,
) -> Dict[str, Any]:
    sources = _configured_sources()
    if not sources:
        _record_sync(
            db, "not_configured", trigger,
            "No official scheme sources are configured on the server.",
        )
        return {
            "ok": False,
            "reason": "not_configured",
            "message": "Official scheme sources are not configured on the server.",
        }
    if not settings.GOV_SCHEMES_API_KEY:
        _record_sync(
            db, "not_configured", trigger,
            "GOV_SCHEMES_API_KEY is not configured on the server.",
        )
        return {
            "ok": False,
            "reason": "not_configured",
            "message": "Official scheme sources are not configured with an API key.",
        }
    if not force:
        last = (
            db.query(SchemeSyncLog)
            .filter(SchemeSyncLog.status == "success")
            .order_by(SchemeSyncLog.synced_at.desc())
            .first()
        )
        if last:
            age = datetime.utcnow() - last.synced_at
            if age < timedelta(minutes=settings.GOV_SCHEMES_REFRESH_MINUTES):
                return {
                    "ok": True,
                    "cached": True,
                    "synced_at": last.synced_at.isoformat(),
                    "records_stored": last.records_stored,
                    "message": f"Served from a recent verification ({int(age.total_seconds() // 60)} minutes ago).",
                }
    if settings.GOV_SCHEMES_REFRESH_MINUTES and not force:
        last_any = (
            db.query(SchemeSyncLog)
            .order_by(SchemeSyncLog.synced_at.desc())
            .first()
        )
        if last_any and (datetime.utcnow() - last_any.synced_at) < timedelta(seconds=60):
            return {
                "ok": True,
                "cached": True,
                "synced_at": last_any.synced_at.isoformat(),
                "records_stored": last_any.records_stored,
                "message": "Refresh rate-limited. Showing the most recent verification.",
            }

    total_fetched = 0
    total_stored = 0
    stored_keys: List[str] = []
    source_reports: List[Dict[str, Any]] = []

    for source in sources:
        label = source["label"]
        url = source["url"]
        try:
            records = _fetch_records(url, source["type"])[:limit]
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                message = "Official source rejected the server API key."
            elif status_code == 429:
                message = "Official source rate limit reached. Try again later."
            else:
                message = f"Official source returned HTTP {status_code}."
            _record_sync(db, "failed", trigger, message, source=label)
            source_reports.append({"source": label, "ok": False, "fetched": 0, "stored": 0, "message": message})
            continue
        except httpx.HTTPError:
            message = "Could not reach the official source (network error)."
            _record_sync(db, "failed", trigger, message, source=label)
            source_reports.append({"source": label, "ok": False, "fetched": 0, "stored": 0, "message": message})
            continue
        except Exception:
            message = "Unexpected error while contacting the official source."
            _record_sync(db, "failed", trigger, message, source=label)
            source_reports.append({"source": label, "ok": False, "fetched": 0, "stored": 0, "message": message})
            continue

        rows = [
            r
            for r in (
                normalize_scheme(rec, settings.GOV_SCHEMES_SOURCE_NAME)
                for rec in records
            )
            if r
        ]
        stored, keys = upsert_schemes(db, rows) if rows else (0, [])
        total_fetched += len(records)
        total_stored += stored
        stored_keys.extend(keys)
        _record_sync(
            db, "success", trigger,
            f"Fetched {len(records)} scheme record(s) from {label}.",
            fetched=len(records), stored=stored, source=label,
        )
        source_reports.append({
            "source": label,
            "ok": True,
            "fetched": len(records),
            "stored": stored,
            "message": f"{len(records)} record(s) received, {stored} stored/updated.",
        })

    any_success = any(r["ok"] for r in source_reports)
    return {
        "ok": any_success,
        "cached": False,
        "synced_at": datetime.utcnow().isoformat(),
        "records_fetched": total_fetched,
        "records_stored": total_stored,
        "stored_ids": stored_keys[:50],
        "sources": source_reports,
        "message": (
            f"Verified {total_fetched} record(s) across {len(source_reports)} source(s), "
            f"{total_stored} stored/updated."
            if any_success
            else "No official source could be reached. No data was changed."
        ),
    }


# ---------------------------------------------------------------------------
# Freshness metadata (honest live/latest/stale/unavailable labels)
# ---------------------------------------------------------------------------

def scheme_freshness(db: Session) -> Dict[str, Any]:
    total = db.query(func.count(GovernmentScheme.id)).scalar() or 0
    last_sync = (
        db.query(SchemeSyncLog)
        .order_by(SchemeSyncLog.synced_at.desc())
        .first()
    )
    last_success = (
        db.query(SchemeSyncLog)
        .filter(SchemeSyncLog.status == "success")
        .order_by(SchemeSyncLog.synced_at.desc())
        .first()
    )
    latest_verified = db.query(func.max(GovernmentScheme.last_verified_at)).scalar()
    now = datetime.utcnow()

    obj = {
        "data_available": total > 0,
        "source_configured": source_configured(),
        "sources": [
            s["label"] for s in _configured_sources()
        ],
        "source": settings.GOV_SCHEMES_SOURCE_NAME,
        "source_url": settings.GOV_SCHEMES_SOURCE_URL,
        "total_schemes": total,
        "latest_verified_timestamp": latest_verified.isoformat() if latest_verified else None,
        "last_sync": {
            "status": last_sync.status,
            "message": last_sync.message,
            "synced_at": last_sync.synced_at.isoformat() if last_sync and last_sync.synced_at else None,
            "records_stored": last_sync.records_stored,
        } if last_sync else None,
    }

    if not source_configured():
        obj["label"] = "not_configured"
        obj["is_live"] = False
        obj["may_be_outdated"] = bool(latest_verified and (now - latest_verified) > timedelta(hours=settings.GOV_SCHEMES_STALE_HOURS))
        return obj

    last_success_at = last_success.synced_at if last_success and last_success.synced_at else None
    if not last_success_at:
        obj["label"] = "unavailable"
        obj["is_live"] = False
        obj["may_be_outdated"] = True
        return obj
    age = now - last_success_at
    if age < timedelta(minutes=settings.GOV_SCHEMES_REFRESH_MINUTES):
        obj["label"] = "live"
        obj["is_live"] = True
        obj["may_be_outdated"] = False
    elif age > timedelta(hours=settings.GOV_SCHEMES_STALE_HOURS):
        obj["label"] = "stale"
        obj["is_live"] = False
        obj["may_be_outdated"] = True
    else:
        obj["label"] = "latest"
        obj["is_live"] = False
        obj["may_be_outdated"] = False
    return obj


def list_states(db: Session) -> List[Dict[str, Any]]:
    """Return all Indian states/UTs with their scheme counts.

    Always returns the full official list of 28 states + 8 Union Territories
    so the filter dropdown is always complete. States with stored schemes get
    their actual count; others show 0.
    """
    INDIAN_STATES = [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
        "Chhattisgarh", "Goa", "Gujarat", "Haryana",
        "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
        "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
        "Mizoram", "Nagaland", "Odisha", "Punjab",
        "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
        "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
        "Andaman and Nicobar Islands", "Chandigarh",
        "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
        "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
    ]
    db_counts: Dict[str, int] = {}
    rows = (
        db.query(GovernmentScheme.state, func.count(GovernmentScheme.id))
        .filter(GovernmentScheme.state.isnot(None), GovernmentScheme.state != "")
        .group_by(GovernmentScheme.state)
        .all()
    )
    for name, count in rows:
        if name and name.strip().lower() not in ("all", "all india", "national", "india"):
            db_counts[name.strip()] = count
    result: List[Dict[str, Any]] = []
    for state_name in sorted(INDIAN_STATES):
        result.append({"name": state_name, "count": db_counts.get(state_name, 0)})
    return result


def auto_sync_if_due(db: Session, trigger: str = "api") -> Optional[Dict[str, Any]]:
    """Lazy, throttled refresh: only runs when a configured source exists and the
    last successful verification is older than the refresh window."""
    if not source_configured():
        return None
    last_success = (
        db.query(SchemeSyncLog)
        .filter(SchemeSyncLog.status == "success")
        .order_by(SchemeSyncLog.synced_at.desc())
        .first()
    )
    if last_success and last_success.synced_at:
        if (datetime.utcnow() - last_success.synced_at) < timedelta(minutes=settings.GOV_SCHEMES_REFRESH_MINUTES):
            return None
    return sync_from_sources(db, trigger=trigger, force=False)
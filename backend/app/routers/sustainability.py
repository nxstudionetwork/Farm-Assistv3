"""Sustainability Dashboard API.

Serves the Sustainability Dashboard with real, farmer-owned data only:

* water usage is read from the existing ``irrigation_records`` table (never
  duplicated here) so the dashboard always matches the Soil & Irrigation page;
* energy usage and sustainable practices come from ``app.models.sustainability``;
* soil indicators come from the existing ``soil_records``;
* crop coverage, farm/field area and sensor status are joined from the existing
  farm, plot, crop-cycle and sensor tables.

Every metric carries an ``available`` flag. When the underlying records do not
exist the dashboard reports the metric as unavailable instead of inventing a
value, and every returned number ships with the formula that produced it.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, SoilRecord, IrrigationRecord
from app.models.sustainability import EnergyUsageRecord, SustainablePracticeRecord
from app.routers.sensors import Sensor
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/sustainability", tags=["Sustainability"])

ENERGY_TYPES = ["electricity", "fuel", "diesel", "solar", "biomass", "other"]
PRACTICE_CATEGORIES = ["soil", "water", "energy", "waste", "biodiversity"]
PRACTICE_STATUSES = ["active", "planned", "completed"]
ENERGY_UNITS = ["kWh", "Litres", "kg"]

WATER_TO_LITRES = {
    "l": 1.0, "ltr": 1.0, "ltrs": 1.0, "lt": 1.0,
    "litre": 1.0, "litres": 1.0, "liter": 1.0, "liters": 1.0,
    "kl": 1000.0, "kilolitre": 1000.0, "kilolitres": 1000.0,
    "kiloliter": 1000.0, "kiloliters": 1000.0, "klitre": 1000.0, "klitres": 1000.0,
    "m3": 1000.0, "m^3": 1000.0, "m\u00b3": 1000.0, "cu.m": 1000.0, "cbm": 1000.0,
}

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

ROW_LIMIT = 100


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _num(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _r2(value: Any) -> Optional[float]:
    n = _num(value)
    return None if n is None else round(n, 2)


def _r1(value: Any) -> Optional[float]:
    n = _num(value)
    return None if n is None else round(n, 1)


def _stamp(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%d") if dt else None


def _avg(values: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), 2) if nums else None


def _sum(values: List[Optional[float]]) -> Optional[float]:
    nums = [v for v in values if v is not None]
    return round(sum(nums), 2) if nums else None


def _litres(quantity: Optional[float], unit: Optional[str]) -> Optional[float]:
    """Normalise a logged water amount to litres so totals stay comparable."""
    if quantity is None:
        return None
    factor = WATER_TO_LITRES.get((unit or "litres").strip().lower(), None)
    if factor is None:
        return None
    return round(quantity * factor, 2)


def _acres(area: Any, unit: Optional[str]) -> Optional[float]:
    n = _num(area)
    if n is None:
        return None
    u = (unit or "acres").strip().lower()
    if u in ("hectare", "hectares", "ha"):
        return round(n * 2.4711, 2)
    if u in ("sq m", "sqm", "m2", "m²"):
        return round(n / 4046.86, 4)
    return round(n, 2)


def _month_key(dt: datetime) -> str:
    return "%04d-%02d" % (dt.year, dt.month)


def _month_label(key: str) -> str:
    try:
        year, month = key.split("-")
        return "%s %s" % (MONTH_LABELS[int(month) - 1], year)
    except (ValueError, IndexError):
        return key


def _parse_date(value: Optional[str], field: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Invalid %s. Use YYYY-MM-DD." % field)


def _period(date_from: Optional[str], date_to: Optional[str]) -> Dict[str, Any]:
    start = _parse_date(date_from, "date_from")
    end = _parse_date(date_to, "date_to")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")
    if end and end.hour == 0 and end.minute == 0 and end.second == 0:
        end = end + timedelta(days=1) - timedelta(seconds=1)
    return {"from": _stamp(start), "to": _stamp(end), "start": start, "end": end}


def _in_period(value: Optional[datetime], period: Dict[str, Any]) -> bool:
    if value is None:
        return period["from"] is None and period["to"] is None
    if period["start"] and value < period["start"]:
        return False
    if period["end"] and value > period["end"]:
        return False
    return True


def _period_label(period: Dict[str, Any]) -> str:
    if not period["from"] and not period["to"]:
        return "All time"
    if period["from"] and period["to"]:
        return "%s to %s" % (period["from"], period["to"])
    if period["from"]:
        return "From %s" % period["from"]
    return "Up to %s" % period["to"]


def _area_text(area: Optional[float], unit: Optional[str]) -> str:
    if area is None:
        return "the recorded farm area"
    return "%.2f %s of farm area" % (area, unit or "Acres")


def _resolve_scope(db: Session, user: User, farm_id: Optional[str] = None,
                   plot_id: Optional[str] = None):
    """Farms/plots owned by the user. Frontend IDs are never trusted."""
    farms_q = db.query(Farm).filter(Farm.user_id == user.id, Farm.is_active == True)
    if farm_id:
        farms_q = farms_q.filter(Farm.id == farm_id)
    farms = farms_q.order_by(Farm.created_at.asc()).all()
    if farm_id and not farms:
        raise HTTPException(status_code=404, detail="Farm not found")

    plots: List[FarmPlot] = []
    farm_ids = [f.id for f in farms]
    if farm_ids:
        plots_q = db.query(FarmPlot).filter(FarmPlot.farm_id.in_(farm_ids))
        if plot_id:
            plots_q = plots_q.filter(FarmPlot.id == plot_id)
        plots = plots_q.order_by(FarmPlot.created_at.asc()).all()
        if plot_id and not plots:
            raise HTTPException(status_code=404, detail="Plot not found")
    elif plot_id:
        raise HTTPException(status_code=404, detail="Plot not found")

    return farms, plots, farm_ids, [p.id for p in plots]


def _active_crop_by_plot(db: Session, plot_ids: List[str]) -> Dict[str, Dict[str, str]]:
    """plot_id -> {crop, stage} for active crop cycles (crop coverage / water by crop)."""
    if not plot_ids:
        return {}
    rows = db.query(CropCycle, Crop).join(
        Crop, CropCycle.crop_id == Crop.id
    ).filter(
        CropCycle.plot_id.in_(plot_ids),
        CropCycle.status == "active",
    ).all()
    out: Dict[str, Dict[str, str]] = {}
    for cycle, crop in rows:
        out.setdefault(cycle.plot_id, {
            "crop": crop.name or "Unnamed crop",
            "stage": cycle.current_stage or "",
        })
    return out


def _is_renewable(record: EnergyUsageRecord) -> bool:
    haystack = " ".join([
        (record.energy_type or "").lower(),
        (record.source or "").lower(),
    ])
    return any(token in haystack for token in ("solar", "wind", "biomass", "renewable", "photovolta"))


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_model=dict)
def sustainability_dashboard(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Real sustainability data for the authenticated farmer.

    Returns summary metrics (with explicit availability flags), record tables,
    chart series, the formula behind every number and data-gap guidance.
    """
    period = _period(date_from, date_to)
    farms, plots, farm_ids, plot_ids = _resolve_scope(db, current_user, farm_id, plot_id)

    farm_map = {f.id: f for f in farms}
    plot_map = {p.id: p for p in plots}
    plot_farm = {p.id: p.farm_id for p in plots}
    crop_by_plot = _active_crop_by_plot(db, plot_ids)

    def _farm_name(plot_or_farm_id: Optional[str]) -> Optional[str]:
        fid = plot_farm.get(plot_or_farm_id, plot_or_farm_id)
        farm = farm_map.get(fid)
        return farm.farm_name if farm else None

    def _plot_name(pid: Optional[str]) -> Optional[str]:
        plot = plot_map.get(pid)
        return plot.plot_name if plot else None

    # ---- water (existing irrigation_records) ----------------------------- #
    irrigation = []
    if plot_ids:
        irrigation = db.query(IrrigationRecord).filter(
            IrrigationRecord.plot_id.in_(plot_ids)
        ).order_by(IrrigationRecord.irrigation_date.desc()).all()
    water_rows = [r for r in irrigation if _in_period(r.irrigation_date, period)]
    water_litres = [
        _litres(r.water_quantity, r.water_unit) for r in water_rows
    ]
    water_total = _sum(water_litres)
    water_known = [v for v in water_litres if v is not None]
    water_minutes = _sum([r.duration_minutes for r in water_rows])

    # ---- energy ---------------------------------------------------------- #
    energy_q = db.query(EnergyUsageRecord).filter(
        EnergyUsageRecord.farmer_id == current_user.id
    )
    if farm_ids:
        energy_q = energy_q.filter(EnergyUsageRecord.farm_id.in_(farm_ids))
    if plot_ids:
        energy_q = energy_q.filter(
            or_(EnergyUsageRecord.plot_id.in_(plot_ids),
                EnergyUsageRecord.plot_id.is_(None))
        )
    energy_all = energy_q.order_by(EnergyUsageRecord.usage_date.desc()).all()
    energy_rows = [r for r in energy_all if _in_period(r.usage_date, period)]
    energy_by_unit: Dict[str, float] = {}
    for record in energy_rows:
        qty = _num(record.quantity) or 0.0
        energy_by_unit[record.unit or "kWh"] = round(
            energy_by_unit.get(record.unit or "kWh", 0.0) + qty, 2
        )
    primary_unit = None
    if energy_by_unit:
        primary_unit = max(energy_by_unit, key=lambda u: energy_by_unit[u])
    energy_total = energy_by_unit.get(primary_unit) if primary_unit else None
    energy_cost = _sum([r.cost for r in energy_rows])
    renewable_total = None
    non_renewable_total = None
    renewable_share = None
    if primary_unit:
        primary_rows = [r for r in energy_rows if r.unit == primary_unit]
        renewable_total = _sum([r.quantity for r in primary_rows if _is_renewable(r)]) or 0.0
        non_renewable_total = _sum([r.quantity for r in primary_rows if not _is_renewable(r)]) or 0.0
        if energy_total:
            renewable_share = round((renewable_total / energy_total) * 100.0, 1)

    # ---- sustainable practices -------------------------------------------- #
    practice_q = db.query(SustainablePracticeRecord).filter(
        SustainablePracticeRecord.farmer_id == current_user.id
    )
    if farm_ids:
        practice_q = practice_q.filter(SustainablePracticeRecord.farm_id.in_(farm_ids))
    if plot_ids:
        practice_q = practice_q.filter(
            or_(SustainablePracticeRecord.plot_id.in_(plot_ids),
                SustainablePracticeRecord.plot_id.is_(None))
        )
    practices_all = practice_q.order_by(
        SustainablePracticeRecord.created_at.desc()).all()
    practice_rows = [p for p in practices_all
                     if _in_period(p.started_on, period) or _in_period(p.created_at, period)]
    practice_by_category: Dict[str, int] = {}
    for record in practice_rows:
        key = (record.category or "other").lower()
        practice_by_category[key] = practice_by_category.get(key, 0) + 1
    practice_area = _sum([p.area_hectares for p in practice_rows])

    # ---- soil (existing soil_records) ------------------------------------ #
    soil = []
    if plot_ids:
        soil = db.query(SoilRecord).filter(SoilRecord.plot_id.in_(plot_ids)).all()
    soil_rows = [s for s in soil if _in_period(s.test_date, period)]
    latest_soil: Dict[str, SoilRecord] = {}
    for record in sorted(soil_rows, key=lambda s: s.test_date or datetime.min):
        latest_soil[record.plot_id] = record
    soil_latest_values = list(latest_soil.values())
    ph_avg = _avg([s.ph_level for s in soil_latest_values])
    om_avg = _avg([s.organic_matter for s in soil_latest_values])
    moisture_avg = _avg([s.moisture for s in soil_latest_values])
    last_soil_date = max([s.test_date for s in soil if s.test_date], default=None)
    days_since_soil = None
    if last_soil_date:
        days_since_soil = (datetime.utcnow() - last_soil_date).days

    # ---- farm / field / crop coverage ------------------------------------- #
    total_area = None
    area_unit = "Acres"
    for farm in farms:
        acres = _acres(farm.total_area, farm.area_unit)
        if acres is None:
            continue
        total_area = round((total_area or 0.0) + acres, 2)
        area_unit = farm.area_unit or "Acres"
    covered_plots = [p for p in plots if p.id in crop_by_plot]
    covered_area = None
    for plot in covered_plots:
        acres = _acres(plot.area, area_unit)
        if acres is None:
            continue
        covered_area = round((covered_area or 0.0) + acres, 2)
    crop_names = sorted({v["crop"] for v in crop_by_plot.values()})
    water_per_acre = None
    if water_total is not None and total_area:
        water_per_acre = round(water_total / total_area, 1)
    energy_per_acre = None
    if energy_total is not None and total_area:
        energy_per_acre = round(energy_total / total_area, 1)

    # ---- sensors ---------------------------------------------------------- #
    sensors_q = db.query(Sensor).filter(Sensor.user_id == current_user.id)
    if farm_ids:
        sensors_q = sensors_q.filter(Sensor.farm_id.in_(farm_ids))
    sensors = sensors_q.all()
    connected_sensors = [s for s in sensors if (s.status or "").lower() == "connected"]
    soil_sensors = [s for s in sensors if "moisture" in (s.sensor_type or "").lower()]

    # ---- monthly series --------------------------------------------------- #
    def _monthly(entries: List[tuple]) -> List[Dict[str, Any]]:
        buckets: Dict[str, float] = {}
        for key, value in entries:
            if value is None:
                continue
            buckets[key] = round(buckets.get(key, 0.0) + value, 2)
        return [
            {"key": key, "label": _month_label(key), "value": buckets[key]}
            for key in sorted(buckets)
        ]

    def _monthly_average(entries: List[tuple]) -> List[Dict[str, Any]]:
        """Average the latest reading of each field per month (never a sum)."""
        buckets: Dict[str, Dict[str, float]] = {}
        for key, source, value in entries:
            if value is None:
                continue
            buckets.setdefault(key, {})[source] = value
        out = []
        for key in sorted(buckets):
            values = list(buckets[key].values())
            out.append({
                "key": key,
                "label": _month_label(key),
                "value": round(sum(values) / len(values), 2) if values else None,
            })
        return out

    water_monthly = _monthly([
        (_month_key(r.irrigation_date), _litres(r.water_quantity, r.water_unit))
        for r in water_rows if r.irrigation_date
    ])
    energy_monthly = _monthly([
        (_month_key(r.usage_date), r.quantity if r.unit == primary_unit else None)
        for r in energy_rows if r.usage_date
    ])
    practices_monthly = _monthly([
        (
            _month_key(p.started_on or p.created_at),
            1.0,
        )
        for p in practice_rows if (p.started_on or p.created_at)
    ])
    soil_monthly_latest: Dict[str, SoilRecord] = {}
    for record in sorted(soil_rows, key=lambda s: s.test_date or datetime.min):
        if record.test_date:
            soil_monthly_latest["%s|%s" % (_month_key(record.test_date), record.plot_id)] = record
    def _soil_trend(field: str) -> List[Dict[str, Any]]:
        return _monthly_average([
            (record.test_date.strftime("%Y-%m"), record.plot_id, getattr(record, field))
            for record in soil_monthly_latest.values()
        ])

    soil_trend = _soil_trend("ph_level")
    soil_om_trend = _soil_trend("organic_matter")
    soil_moisture_trend = _soil_trend("moisture")

    water_by_plot: Dict[str, float] = {}
    for record in water_rows:
        litres = _litres(record.water_quantity, record.water_unit)
        if litres is None:
            continue
        name = _plot_name(record.plot_id) or "Unknown field"
        water_by_plot[name] = round(water_by_plot.get(name, 0.0) + litres, 2)
    water_by_crop: Dict[str, float] = {}
    for record in water_rows:
        litres = _litres(record.water_quantity, record.water_unit)
        if litres is None:
            continue
        crop = crop_by_plot.get(record.plot_id, {}).get("crop") or "No active crop"
        water_by_crop[crop] = round(water_by_crop.get(crop, 0.0) + litres, 2)

    def _series(mapping: Dict[str, float]) -> List[Dict[str, Any]]:
        return sorted(
            [{"key": k, "label": k, "value": v} for k, v in mapping.items()],
            key=lambda row: row["value"], reverse=True,
        )

    # ---- record tables ---------------------------------------------------- #
    water_table = [{
        "date": _stamp(r.irrigation_date),
        "farm": _farm_name(r.plot_id),
        "plot": _plot_name(r.plot_id),
        "crop": crop_by_plot.get(r.plot_id, {}).get("crop"),
        "amount": _r2(r.water_quantity),
        "unit": r.water_unit or "Litres",
        "litres": _litres(r.water_quantity, r.water_unit),
        "method": r.method,
        "duration_minutes": _r2(r.duration_minutes),
    } for r in water_rows[:ROW_LIMIT]]

    energy_table = [{
        "id": r.id,
        "date": _stamp(r.usage_date),
        "farm": farm_map[r.farm_id].farm_name if r.farm_id in farm_map else None,
        "plot": _plot_name(r.plot_id),
        "source": r.source,
        "energy_type": r.energy_type,
        "quantity": _r2(r.quantity),
        "unit": r.unit,
        "renewable": _is_renewable(r),
        "cost": _r2(r.cost),
        "notes": r.notes,
    } for r in energy_rows[:ROW_LIMIT]]

    practice_table = [{
        "id": r.id,
        "practice": r.practice_name,
        "farm": farm_map[r.farm_id].farm_name if r.farm_id in farm_map else None,
        "plot": _plot_name(r.plot_id),
        "category": r.category,
        "status": r.status,
        "area_hectares": _r2(r.area_hectares),
        "started_on": _stamp(r.started_on),
        "notes": r.notes,
    } for r in practice_rows[:ROW_LIMIT]]

    soil_table = [{
        "date": _stamp(s.test_date),
        "farm": _farm_name(s.plot_id),
        "plot": _plot_name(s.plot_id),
        "ph": _r2(s.ph_level),
        "nitrogen": _r2(s.nitrogen),
        "phosphorus": _r2(s.phosphorus),
        "potassium": _r2(s.potassium),
        "organic_matter": _r2(s.organic_matter),
        "moisture": _r2(s.moisture),
        "soil_type": s.soil_type,
    } for s in sorted(soil_rows, key=lambda s: s.test_date or datetime.min,
                      reverse=True)[:ROW_LIMIT]]

    # ---- summary metrics -------------------------------------------------- #
    water_count = len(water_rows)
    energy_count = len(energy_rows)
    practice_count = len(practice_rows)
    soil_count = len(soil_rows)
    total_records = water_count + energy_count + practice_count + soil_count

    summary = {
        "area": {
            "available": total_area is not None,
            "farms": len(farms),
            "plots": len(plots),
            "total": total_area,
            "unit": area_unit if total_area is not None else "Acres",
        },
        "water_usage": {
            "available": bool(water_known),
            "value": water_total,
            "unit": "Litres",
            "records": water_count,
            "irrigation_minutes": water_minutes,
            "per_acre": water_per_acre,
            "methods": sorted({r.method for r in water_rows if r.method}),
            "unmeasured_records": water_count - len(water_known),
        },
        "water_saved": {
            "available": False,
            "value": None,
            "unit": "Litres",
            "water_practices": practice_by_category.get("water", 0),
            "reason": "Farm Assist does not estimate water saved: there is no earlier water-usage baseline on record to compare against. Water-saving practices recorded: %d." % (
                practice_by_category.get("water", 0)),
        },
        "energy_usage": {
            "available": energy_total is not None,
            "value": energy_total,
            "unit": primary_unit,
            "records": energy_count,
            "cost": energy_cost,
            "per_acre": energy_per_acre,
            "by_unit": energy_by_unit,
        },
        "renewable_energy": {
            "available": renewable_share is not None,
            "value": renewable_total,
            "unit": primary_unit,
            "share_pct": renewable_share,
            "non_renewable": non_renewable_total,
            "reason": None if renewable_share is not None
            else "Record energy usage with a solar or biomass source to see the renewable share.",
        },
        "soil_health": {
            "available": bool(soil_count),
            "tests": soil_count,
            "ph": ph_avg,
            "organic_matter": om_avg,
            "moisture": moisture_avg,
            "plots_tested": len(latest_soil),
            "last_test": _stamp(last_soil_date),
            "days_since_test": days_since_soil,
        },
        "practices": {
            "available": bool(practice_count),
            "count": practice_count,
            "area_hectares": practice_area,
            "by_category": practice_by_category,
            "active": len([p for p in practice_rows if (p.status or "").lower() == "active"]),
        },
        "crop_coverage": {
            "available": bool(crop_by_plot),
            "plots_with_crops": len(covered_plots),
            "plots": len(plots),
            "area": covered_area,
            "unit": area_unit,
            "crops": crop_names,
        },
        "waste": {
            "available": bool(practice_by_category.get("waste")),
            "count": practice_by_category.get("waste", 0),
            "unit": "practice records",
            "reason": None if practice_by_category.get("waste")
            else "No waste or compost practice has been recorded yet.",
        },
        "records": {
            "available": bool(total_records),
            "count": total_records,
            "water": water_count,
            "energy": energy_count,
            "practices": practice_count,
            "soil": soil_count,
        },
    }

    # ---- transparent formulas --------------------------------------------- #
    calculations = [
        {
            "metric": "Farm area",
            "formula": "Sum of farm.total_area converted to %s (hectares x 2.4711, m2 / 4046.86)." % area_unit,
            "records": len(farms),
        },
        {
            "metric": "Total water usage",
            "formula": "Sum of water_quantity on your irrigation records, normalised to litres (1 kL or 1 m3 = 1000 L).",
            "records": water_count,
        },
        {
            "metric": "Water per acre",
            "formula": "Total water usage (L) / farm area (%s)." % area_unit,
            "records": water_count,
        },
        {
            "metric": "Soil indicators",
            "formula": "Average of the most recent soil test per field (pH, organic matter %, moisture %).",
            "records": soil_count,
        },
        {
            "metric": "Energy usage",
            "formula": "Sum of quantity grouped by unit; the largest unit group is shown as the headline total.",
            "records": energy_count,
        },
        {
            "metric": "Renewable share",
            "formula": "Energy records whose type or source mentions solar, wind, biomass or renewable / total energy x 100.",
            "records": energy_count,
        },
        {
            "metric": "Crop coverage",
            "formula": "Fields with an active crop cycle, with their area and crop names from your existing crop cycles.",
            "records": len(covered_plots),
        },
        {
            "metric": "Sustainability records",
            "formula": "Irrigation + energy + practice + soil records inside the selected period.",
            "records": total_records,
        },
    ]

    # ---- guidance from real gaps ------------------------------------------ #
    guidance: List[Dict[str, str]] = []
    if not farms:
        guidance.append({
            "severity": "high",
            "title": "Add your first farm",
            "detail": "Sustainability data is grouped by farm and field, so nothing can be calculated until a farm exists.",
            "action": "Go to My Farm",
            "href": "farm.html",
        })
    if not soil_count:
        guidance.append({
            "severity": "high",
            "title": "No soil test recorded",
            "detail": "Soil pH, organic matter and moisture indicators come from soil tests. None are recorded for this selection.",
            "action": "Record a soil test",
            "href": "soil-irrigation.html",
        })
    elif days_since_soil is not None and days_since_soil > 90:
        guidance.append({
            "severity": "medium",
            "title": "Soil test is over 90 days old",
            "detail": "Your latest soil test was on %s (%d days ago). A fresh test keeps the soil indicators current." % (
                _stamp(last_soil_date), days_since_soil),
            "action": "Record a soil test",
            "href": "soil-irrigation.html",
        })
    if not water_count:
        guidance.append({
            "severity": "high",
            "title": "No irrigation records in this period",
            "detail": "Total water usage and water-per-acre are calculated from the irrigation records you log on Soil & Irrigation.",
            "action": "Log irrigation",
            "href": "soil-irrigation.html",
        })
    elif not water_known:
        guidance.append({
            "severity": "medium",
            "title": "Irrigation amounts are missing",
            "detail": "%d irrigation record(s) have no water amount, so litres used cannot be totalled." % (
                water_count - len(water_known)),
            "action": "Update irrigation records",
            "href": "soil-irrigation.html",
        })
    if not energy_count:
        guidance.append({
            "severity": "medium",
            "title": "No energy usage recorded",
            "detail": "Pump, diesel, electricity and solar usage are recorded here. None are saved yet, so energy metrics stay unavailable.",
            "action": "Add energy record",
            "href": "#add-energy",
        })
    if not energy_count or renewable_share is None:
        guidance.append({
            "severity": "medium",
            "title": "Renewable energy not tracked",
            "detail": "Add solar or biomass energy records to see the renewable share of your farm energy use.",
            "action": "Add energy record",
            "href": "#add-energy",
        })
    elif renewable_share == 0:
        guidance.append({
            "severity": "low",
            "title": "No renewable energy recorded",
            "detail": "All %s of recorded energy came from non-renewable sources. A solar pump or biomass unit would raise the renewable share."
                    % (primary_unit or "kWh"),
            "action": "Add energy record",
            "href": "#add-energy",
        })
    if not practice_count:
        guidance.append({
            "severity": "medium",
            "title": "No sustainable practice records",
            "detail": "Practices such as cover cropping, composting, mulching or drip irrigation are tracked here and power the practice counts.",
            "action": "Add practice record",
            "href": "#add-practice",
        })
    elif practice_count < 3:
        guidance.append({
            "severity": "low",
            "title": "Only %d practice record(s) so far" % practice_count,
            "detail": "Recording at least one practice per category gives a fuller picture of your sustainability effort.",
            "action": "Add practice record",
            "href": "#add-practice",
        })
    if not practice_by_category.get("waste"):
        guidance.append({
            "severity": "low",
            "title": "No waste or compost practice",
            "detail": "Composting and residue recycling practices are recorded under the waste category.",
            "action": "Add practice record",
            "href": "#add-practice",
        })
    if not soil_sensors:
        guidance.append({
            "severity": "low",
            "title": "No soil moisture sensor connected",
            "detail": "A connected soil moisture sensor logs water readings automatically, so irrigation records stay complete without manual entry.",
            "action": "Connect a sensor",
            "href": "sensors.html",
        })
    if not guidance:
        guidance.append({
            "severity": "low",
            "title": "Sustainability data is up to date",
            "detail": "Soil, irrigation, energy and practice records are all present for this selection. Keep logging as the season progresses.",
            "action": "Add another record",
            "href": "#add-energy",
        })

    notes: List[str] = []
    if not farms:
        notes.append("No farm found for this account yet.")
    elif not plots:
        notes.append("No fields added to this farm yet. Add fields to record water, soil and energy per field.")
    if energy_by_unit and len(energy_by_unit) > 1:
        notes.append("Energy is recorded in more than one unit (%s). Totals are shown for %s only." % (
            ", ".join(sorted(energy_by_unit)), primary_unit))
    if not total_records:
        notes.append("No sustainability records available yet.")
    elif any(not summary[key]["available"] for key in (
        "water_usage", "energy_usage", "soil_health", "practices"
    )):
        notes.append("Some sustainability information is not available yet.")

    scope_label = "All farms"
    if farm_id and len(farms) == 1:
        scope_label = farms[0].farm_name
        if plot_id and len(plots) == 1:
            scope_label = "%s - %s" % (scope_label, plots[0].plot_name)

    return {
        "status": "success",
        "data": {
            "farmer": {
                "name": current_user.full_name or "Farmer",
                "farmer_id": current_user.farmer_id or current_user.id,
            },
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            "period": {"from": period["from"], "to": period["to"], "label": _period_label(period)},
            "scope": {
                "farm_id": farm_id,
                "farm_name": farms[0].farm_name if farm_id and len(farms) == 1 else None,
                "plot_id": plot_id,
                "plot_name": plots[0].plot_name if plot_id and len(plots) == 1 else None,
                "label": scope_label,
                "farms_count": len(farms),
                "plots_count": len(plots),
            },
            "farms": [{
                "id": f.id,
                "farm_name": f.farm_name,
                "district": f.district,
                "state": f.state,
                "total_area": f.total_area,
                "area_unit": f.area_unit or "Acres",
                "plots": [{
                    "id": p.id,
                    "plot_name": p.plot_name,
                    "area": p.area,
                } for p in sorted(f.plots, key=lambda p: p.created_at or datetime.min)],
            } for f in farms],
            "single_farm": len(farms) == 1,
            "single_plot": len(plots) == 1 and (not farm_id or len(farms) == 1),
            "summary": summary,
            "records": {
                "water": water_table,
                "energy": energy_table,
                "practices": practice_table,
                "soil": soil_table,
            },
            "truncated": {
                "water": len(water_rows) > ROW_LIMIT,
                "energy": len(energy_rows) > ROW_LIMIT,
                "practices": len(practice_rows) > ROW_LIMIT,
                "soil": len(soil_rows) > ROW_LIMIT,
            },
            "trends": {
                "water_monthly": water_monthly,
                "energy_monthly": energy_monthly,
                "soil_ph": soil_trend,
                "soil_organic_matter": soil_om_trend,
                "soil_moisture": soil_moisture_trend,
                "practices_monthly": practices_monthly,
                "water_by_plot": _series(water_by_plot),
                "water_by_crop": _series(water_by_crop),
                "water_unit": "Litres",
                "energy_unit": primary_unit,
                "soil_trend_basis": "Average of the most recent soil test per field in each month.",
                "energy_split": {
                    "available": renewable_share is not None,
                    "unit": primary_unit,
                    "renewable": renewable_total,
                    "non_renewable": non_renewable_total,
                    "share_pct": renewable_share,
                },
            },
            "indicators": [
                {
                    "key": "soil_ph", "label": "Average soil pH", "unit": "",
                    "value": ph_avg, "available": ph_avg is not None,
                    "basis": "Average of the most recent soil test per field",
                },
                {
                    "key": "soil_om", "label": "Average organic matter", "unit": "%",
                    "value": om_avg, "available": om_avg is not None,
                    "basis": "Average of the most recent soil test per field",
                },
                {
                    "key": "soil_moisture", "label": "Average soil moisture", "unit": "%",
                    "value": moisture_avg, "available": moisture_avg is not None,
                    "basis": "Average of the most recent soil test per field",
                },
                {
                    "key": "water_per_acre", "label": "Water per acre", "unit": "L",
                    "value": water_per_acre, "available": water_per_acre is not None,
                    "basis": "Total water %s over %s" % (
                        _period_label(period).lower(),
                        _area_text(total_area, area_unit),
                    ),
                },
                {
                    "key": "energy_per_acre", "label": "Energy per acre", "unit": primary_unit or "kWh",
                    "value": energy_per_acre, "available": energy_per_acre is not None,
                    "basis": "Total energy %s over %s" % (
                        _period_label(period).lower(),
                        _area_text(total_area, area_unit),
                    ),
                },
                {
                    "key": "renewable_share", "label": "Renewable energy share", "unit": "%",
                    "value": renewable_share, "available": renewable_share is not None,
                    "basis": "Renewable energy / total energy x 100",
                },
                {
                    "key": "practice_area", "label": "Area under sustainable practices", "unit": "ha",
                    "value": practice_area, "available": practice_area is not None,
                    "basis": "Sum of area_hectares on practice records",
                },
            ],
            "calculations": calculations,
            "guidance": guidance,
            "notes": notes,
            "sensors": {
                "total": len(sensors),
                "connected": len(connected_sensors),
                "soil_moisture": len(soil_sensors),
            },
        },
    }


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
class EnergyRecordIn(BaseModel):
    farm_id: str = Field(..., min_length=1, max_length=36)
    plot_id: Optional[str] = Field(None, max_length=36)
    energy_type: str = Field(..., min_length=1, max_length=50)
    quantity: float = Field(..., ge=0)
    unit: str = Field("kWh", max_length=20)
    source: Optional[str] = Field(None, max_length=80)
    cost: Optional[float] = Field(None, ge=0)
    usage_date: str = Field(..., max_length=30)
    notes: Optional[str] = Field(None, max_length=1000)


class PracticeRecordIn(BaseModel):
    farm_id: str = Field(..., min_length=1, max_length=36)
    plot_id: Optional[str] = Field(None, max_length=36)
    practice_name: str = Field(..., min_length=2, max_length=120)
    category: str = Field("soil", max_length=60)
    status: str = Field("active", max_length=30)
    area_hectares: Optional[float] = Field(None, ge=0)
    started_on: Optional[str] = Field(None, max_length=30)
    notes: Optional[str] = Field(None, max_length=1000)


def _own_farm(db: Session, user: User, farm_id: str) -> Farm:
    farm = db.query(Farm).filter(
        Farm.id == farm_id, Farm.user_id == user.id, Farm.is_active == True
    ).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


def _own_plot(db: Session, farm: Farm, plot_id: Optional[str]) -> Optional[FarmPlot]:
    if not plot_id:
        return None
    plot = db.query(FarmPlot).filter(
        FarmPlot.id == plot_id, FarmPlot.farm_id == farm.id
    ).first()
    if not plot:
        raise HTTPException(status_code=404, detail="Plot not found for this farm")
    return plot


@router.post("/energy", status_code=201, response_model=dict)
def create_energy_record(
    payload: EnergyRecordIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save an energy usage record against the authenticated farmer's farm/field."""
    farm = _own_farm(db, current_user, payload.farm_id)
    plot = _own_plot(db, farm, payload.plot_id)
    usage_date = _parse_date(payload.usage_date, "usage_date")
    day_start = usage_date.replace(hour=0, minute=0, second=0, microsecond=0)
    energy_type = payload.energy_type.strip().lower()
    if energy_type not in ENERGY_TYPES:
        raise HTTPException(
            status_code=400,
            detail="energy_type must be one of: %s" % ", ".join(ENERGY_TYPES),
        )
    unit = (payload.unit or "kWh").strip()
    if unit not in ENERGY_UNITS:
        raise HTTPException(
            status_code=400,
            detail="unit must be one of: %s" % ", ".join(ENERGY_UNITS),
        )

    existing = db.query(EnergyUsageRecord).filter(
        EnergyUsageRecord.farmer_id == current_user.id,
        EnergyUsageRecord.farm_id == farm.id,
        EnergyUsageRecord.energy_type == energy_type,
        EnergyUsageRecord.usage_date >= day_start,
        EnergyUsageRecord.usage_date < day_start + timedelta(days=1),
    )
    if payload.plot_id:
        existing = existing.filter(EnergyUsageRecord.plot_id == plot.id)
    else:
        existing = existing.filter(EnergyUsageRecord.plot_id.is_(None))
    record = existing.first()

    created = record is None
    if record is None:
        record = EnergyUsageRecord(
            farmer_id=current_user.id,
            farm_id=farm.id,
            plot_id=plot.id if plot else None,
            energy_type=energy_type,
        )
        db.add(record)
    record.source = (payload.source or "").strip() or None
    record.quantity = float(payload.quantity)
    record.unit = unit
    record.cost = payload.cost
    record.usage_date = usage_date
    record.notes = (payload.notes or "").strip() or None

    db.commit()
    db.refresh(record)
    return {
        "status": "success",
        "data": {
            "created": created,
            "record": {
                "id": record.id,
                "farm_id": record.farm_id,
                "farm_name": farm.farm_name,
                "plot_id": record.plot_id,
                "plot_name": plot.plot_name if plot else None,
                "energy_type": record.energy_type,
                "source": record.source,
                "quantity": _r2(record.quantity),
                "unit": record.unit,
                "cost": _r2(record.cost),
                "usage_date": _stamp(record.usage_date),
                "notes": record.notes,
            },
        },
    }


@router.post("/practices", status_code=201, response_model=dict)
def create_practice_record(
    payload: PracticeRecordIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a sustainable practice against the authenticated farmer's farm/field."""
    farm = _own_farm(db, current_user, payload.farm_id)
    plot = _own_plot(db, farm, payload.plot_id)
    category = (payload.category or "soil").strip().lower()
    if category not in PRACTICE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="category must be one of: %s" % ", ".join(PRACTICE_CATEGORIES),
        )
    status = (payload.status or "active").strip().lower()
    if status not in PRACTICE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be one of: %s" % ", ".join(PRACTICE_STATUSES),
        )
    started_on = _parse_date(payload.started_on, "started_on")
    name = payload.practice_name.strip()

    query = db.query(SustainablePracticeRecord).filter(
        SustainablePracticeRecord.farmer_id == current_user.id,
        SustainablePracticeRecord.farm_id == farm.id,
        SustainablePracticeRecord.practice_name == name,
    )
    if payload.plot_id:
        query = query.filter(SustainablePracticeRecord.plot_id == plot.id)
    else:
        query = query.filter(SustainablePracticeRecord.plot_id.is_(None))
    record = query.first()

    created = record is None
    if record is None:
        record = SustainablePracticeRecord(
            farmer_id=current_user.id,
            farm_id=farm.id,
            plot_id=plot.id if plot else None,
            practice_name=name,
        )
        db.add(record)
    record.category = category
    record.status = status
    record.area_hectares = payload.area_hectares
    record.started_on = started_on
    record.notes = (payload.notes or "").strip() or None

    db.commit()
    db.refresh(record)
    return {
        "status": "success",
        "data": {
            "created": created,
            "record": {
                "id": record.id,
                "farm_id": record.farm_id,
                "farm_name": farm.farm_name,
                "plot_id": record.plot_id,
                "plot_name": plot.plot_name if plot else None,
                "practice_name": record.practice_name,
                "category": record.category,
                "status": record.status,
                "area_hectares": _r2(record.area_hectares),
                "started_on": _stamp(record.started_on),
                "notes": record.notes,
            },
        },
    }


@router.delete("/energy/{record_id}", response_model=dict)
def delete_energy_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(EnergyUsageRecord).filter(
        EnergyUsageRecord.id == record_id,
        EnergyUsageRecord.farmer_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Energy record not found")
    db.delete(record)
    db.commit()
    return {"status": "success", "data": {"deleted": True}}


@router.delete("/practices/{record_id}", response_model=dict)
def delete_practice_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(SustainablePracticeRecord).filter(
        SustainablePracticeRecord.id == record_id,
        SustainablePracticeRecord.farmer_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Practice record not found")
    db.delete(record)
    db.commit()
    return {"status": "success", "data": {"deleted": True}}

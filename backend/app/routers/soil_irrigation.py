"""Soil & Irrigation API.

Provides soil health data, irrigation records, and crop-specific insights
for the authenticated farmer's farms and plots. All data is isolated to the
authenticated user's farms - no farmer can access another farmer's data.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.models.crop import Crop, CropCycle, SoilRecord, IrrigationRecord
from app.utils.auth import get_current_user
from app.services.ai_service import chat_with_ai

router = APIRouter(prefix="/api/v1/soil-irrigation", tags=["Soil & Irrigation"])


def _now():
    return datetime.utcnow()


def _stamp(dt: Optional[datetime]):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def _resolve_scope(db: Session, user: User, farm_id: Optional[str] = None, plot_id: Optional[str] = None):
    """Resolve authorized farms and plots for the user.
    
    Never trusts frontend IDs - every farm must belong to user, every plot to farm.
    """
    farms_q = db.query(Farm).filter(Farm.user_id == user.id, Farm.is_active == True)
    if farm_id:
        farm = farms_q.filter(Farm.id == farm_id).first()
        if not farm:
            raise HTTPException(status_code=404, detail="Farm not found")
        farm_objs = [farm]
    else:
        farm_objs = farms_q.all()
    
    plots = []
    for f in farm_objs:
        p_q = db.query(FarmPlot).filter(FarmPlot.farm_id == f.id)
        if plot_id:
            p = p_q.filter(FarmPlot.id == plot_id).first()
            if not p:
                raise HTTPException(status_code=404, detail="Plot not found")
            plots.append(p)
        else:
            plots.extend(p_q.all())
    return farm_objs, plots


@router.get("/soil-records", response_model=dict)
def get_soil_records(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get soil records for the authenticated farmer's farms/plots."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    q = db.query(SoilRecord).filter(SoilRecord.plot_id.in_(plot_ids))
    
    # Filter by crop if specified
    if crop_id:
        # Get plot IDs that have this crop in active cycles
        crop_plot_ids = [
            cycle.plot_id 
            for cycle in db.query(CropCycle).filter(
                CropCycle.crop_id == crop_id,
                CropCycle.plot_id.in_(plot_ids),
                CropCycle.status == "active"
            ).all()
        ]
        if crop_plot_ids:
            q = q.filter(SoilRecord.plot_id.in_(crop_plot_ids))
        else:
            return {"status": "success", "data": []}
    
    records = q.order_by(SoilRecord.test_date.desc()).limit(limit).all()
    
    # Enrich with plot and farm info
    plot_map = {p.id: p for p in plots}
    farm_map = {f.id: f for f in farm_objs}
    
    return {
        "status": "success",
        "data": [
            {
                "id": r.id,
                "plot_id": r.plot_id,
                "plot_name": plot_map.get(r.plot_id).plot_name if plot_map.get(r.plot_id) else None,
                "farm_id": plot_map.get(r.plot_id).farm_id if plot_map.get(r.plot_id) else None,
                "farm_name": farm_map.get(plot_map.get(r.plot_id).farm_id).farm_name if plot_map.get(r.plot_id) and farm_map.get(plot_map.get(r.plot_id).farm_id) else None,
                "ph_level": r.ph_level,
                "nitrogen": r.nitrogen,
                "phosphorus": r.phosphorus,
                "potassium": r.potassium,
                "organic_matter": r.organic_matter,
                "moisture": r.moisture,
                "soil_type": r.soil_type,
                "test_date": _stamp(r.test_date),
                "notes": r.notes,
            }
            for r in records
        ],
    }


@router.get("/soil-latest", response_model=dict)
def get_latest_soil_data(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the latest soil reading for each plot in scope."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    # Filter by crop if specified
    if crop_id:
        crop_plot_ids = [
            cycle.plot_id 
            for cycle in db.query(CropCycle).filter(
                CropCycle.crop_id == crop_id,
                CropCycle.plot_id.in_(plot_ids),
                CropCycle.status == "active"
            ).all()
        ]
        if crop_plot_ids:
            plot_ids = crop_plot_ids
        else:
            return {"status": "success", "data": {}}
    
    latest_data = {}
    plot_map = {p.id: p for p in plots}
    farm_map = {f.id: f for f in farm_objs}
    
    for pid in plot_ids:
        latest = db.query(SoilRecord).filter(
            SoilRecord.plot_id == pid
        ).order_by(SoilRecord.test_date.desc()).first()
        
        if latest:
            plot = plot_map.get(pid)
            latest_data[pid] = {
                "plot_id": pid,
                "plot_name": plot.plot_name if plot else None,
                "farm_id": plot.farm_id if plot else None,
                "farm_name": farm_map.get(plot.farm_id).farm_name if plot and farm_map.get(plot.farm_id) else None,
                "ph_level": latest.ph_level,
                "nitrogen": latest.nitrogen,
                "phosphorus": latest.phosphorus,
                "potassium": latest.potassium,
                "organic_matter": latest.organic_matter,
                "moisture": latest.moisture,
                "soil_type": latest.soil_type,
                "test_date": _stamp(latest.test_date),
                "notes": latest.notes,
            }
    
    return {
        "status": "success",
        "data": latest_data,
    }


@router.get("/irrigation-records", response_model=dict)
def get_irrigation_records(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get irrigation records for the authenticated farmer's farms/plots."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    since = _now() - timedelta(days=days)
    q = db.query(IrrigationRecord).filter(
        IrrigationRecord.plot_id.in_(plot_ids),
        IrrigationRecord.irrigation_date >= since
    )
    
    # Filter by crop if specified
    if crop_id:
        crop_plot_ids = [
            cycle.plot_id 
            for cycle in db.query(CropCycle).filter(
                CropCycle.crop_id == crop_id,
                CropCycle.plot_id.in_(plot_ids),
                CropCycle.status == "active"
            ).all()
        ]
        if crop_plot_ids:
            q = q.filter(IrrigationRecord.plot_id.in_(crop_plot_ids))
        else:
            return {"status": "success", "data": []}
    
    records = q.order_by(IrrigationRecord.irrigation_date.desc()).limit(limit).all()
    
    # Enrich with plot and farm info
    plot_map = {p.id: p for p in plots}
    farm_map = {f.id: f for f in farm_objs}
    
    return {
        "status": "success",
        "data": [
            {
                "id": r.id,
                "plot_id": r.plot_id,
                "plot_name": plot_map.get(r.plot_id).plot_name if plot_map.get(r.plot_id) else None,
                "farm_id": plot_map.get(r.plot_id).farm_id if plot_map.get(r.plot_id) else None,
                "farm_name": farm_map.get(plot_map.get(r.plot_id).farm_id).farm_name if plot_map.get(r.plot_id) and farm_map.get(plot_map.get(r.plot_id).farm_id) else None,
                "method": r.method,
                "duration_minutes": r.duration_minutes,
                "water_quantity": r.water_quantity,
                "water_unit": r.water_unit,
                "irrigation_date": _stamp(r.irrigation_date),
                "notes": r.notes,
            }
            for r in records
        ],
    }


@router.get("/irrigation-summary", response_model=dict)
def get_irrigation_summary(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get irrigation summary statistics for the scope."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    # Filter by crop if specified
    if crop_id:
        crop_plot_ids = [
            cycle.plot_id 
            for cycle in db.query(CropCycle).filter(
                CropCycle.crop_id == crop_id,
                CropCycle.plot_id.in_(plot_ids),
                CropCycle.status == "active"
            ).all()
        ]
        if crop_plot_ids:
            plot_ids = crop_plot_ids
        else:
            return {
                "status": "success",
                "data": {
                    "total_irrigations": 0,
                    "total_water_used": 0,
                    "total_duration_minutes": 0,
                    "last_irrigation": None,
                    "most_common_method": None,
                }
            }
    
    since = _now() - timedelta(days=days)
    records = db.query(IrrigationRecord).filter(
        IrrigationRecord.plot_id.in_(plot_ids),
        IrrigationRecord.irrigation_date >= since
    ).all()
    
    total_irrigations = len(records)
    total_water = sum(r.water_quantity or 0 for r in records)
    total_duration = sum(r.duration_minutes or 0 for r in records)
    
    last_irrigation = None
    if records:
        latest = max(records, key=lambda r: r.irrigation_date)
        last_irrigation = _stamp(latest.irrigation_date)
    
    # Most common method
    method_counts = {}
    for r in records:
        if r.method:
            method_counts[r.method] = method_counts.get(r.method, 0) + 1
    most_common_method = max(method_counts.keys(), key=method_counts.get) if method_counts else None
    
    return {
        "status": "success",
        "data": {
            "total_irrigations": total_irrigations,
            "total_water_used": total_water,
            "total_duration_minutes": total_duration,
            "last_irrigation": last_irrigation,
            "most_common_method": most_common_method,
        },
    }


@router.get("/crop-context", response_model=dict)
def get_crop_context(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all crops currently planted in the farmer's farms/plots."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    # Get active crop cycles
    cycles = db.query(CropCycle).filter(
        CropCycle.plot_id.in_(plot_ids),
        CropCycle.status == "active"
    ).all()
    
    # Enrich with crop and plot info
    plot_map = {p.id: p for p in plots}
    farm_map = {f.id: f for f in farm_objs}
    
    crop_context = []
    for cycle in cycles:
        crop = db.query(Crop).get(cycle.crop_id)
        plot = plot_map.get(cycle.plot_id)
        if crop and plot:
            crop_context.append({
                "cycle_id": cycle.cycle_id,
                "crop_id": crop.id,
                "crop_name": crop.name,
                "crop_variety": crop.variety,
                "plot_id": plot.id,
                "plot_name": plot.plot_name,
                "farm_id": plot.farm_id,
                "farm_name": farm_map.get(plot.farm_id).farm_name if farm_map.get(plot.farm_id) else None,
                "sowing_date": cycle.sowing_date,
                "expected_harvest_date": cycle.expected_harvest_date,
                "current_stage": cycle.current_stage,
                "irrigation_schedule": cycle.irrigation_schedule,
            })
    
    return {
        "status": "success",
        "data": crop_context,
    }


@router.get("/ai-overview", response_model=dict)
async def get_ai_overview(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    crop_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate AI-powered overview of soil and irrigation conditions."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    # Get latest soil data
    soil_data = []
    for pid in plot_ids:
        latest = db.query(SoilRecord).filter(
            SoilRecord.plot_id == pid
        ).order_by(SoilRecord.test_date.desc()).first()
        if latest:
            plot = db.query(FarmPlot).get(pid)
            soil_data.append({
                "plot": plot.plot_name if plot else "Unknown",
                "ph": latest.ph_level,
                "nitrogen": latest.nitrogen,
                "phosphorus": latest.phosphorus,
                "potassium": latest.potassium,
                "moisture": latest.moisture,
                "organic_matter": latest.organic_matter,
                "test_date": _stamp(latest.test_date),
            })
    
    # Get recent irrigation data
    since = _now() - timedelta(days=7)
    irr_data = []
    for pid in plot_ids:
        recent = db.query(IrrigationRecord).filter(
            IrrigationRecord.plot_id == pid,
            IrrigationRecord.irrigation_date >= since
        ).order_by(IrrigationRecord.irrigation_date.desc()).first()
        if recent:
            plot = db.query(FarmPlot).get(pid)
            irr_data.append({
                "plot": plot.plot_name if plot else "Unknown",
                "method": recent.method,
                "duration": recent.duration_minutes,
                "water_quantity": recent.water_quantity,
                "date": _stamp(recent.irrigation_date),
            })
    
    # Get crop context
    crop_info = ""
    if crop_id:
        crop = db.query(Crop).get(crop_id)
        if crop:
            crop_info = f"Selected Crop: {crop.name}"
    else:
        # Get all active crops
        cycles = db.query(CropCycle).filter(
            CropCycle.plot_id.in_(plot_ids),
            CropCycle.status == "active"
        ).all()
        crop_names = []
        for cycle in cycles:
            crop = db.query(Crop).get(cycle.crop_id)
            if crop:
                crop_names.append(crop.name)
        if crop_names:
            crop_info = f"Active Crops: {', '.join(set(crop_names))}"
    
    # Build context for AI
    context_lines = [
        f"Farmer: {current_user.full_name}",
        f"Farms: {', '.join([f.farm_name for f in farm_objs])}",
        f"Plots: {', '.join([p.plot_name for p in plots])}",
        crop_info,
    ]
    
    if soil_data:
        context_lines.append("\nSOIL DATA (Latest readings):")
        for s in soil_data:
            context_lines.append(
                f"- {s['plot']}: pH={s['ph']}, N={s['nitrogen']} mg/kg, "
                f"P={s['phosphorus']} mg/kg, K={s['potassium']} mg/kg, "
                f"Moisture={s['moisture']}%, Organic Matter={s['organic_matter']}%, "
                f"Tested: {s['test_date']}"
            )
    
    if irr_data:
        context_lines.append("\nIRRIGATION DATA (Last 7 days):")
        for i in irr_data:
            context_lines.append(
                f"- {i['plot']}: {i['method']}, {i['duration']} min, "
                f"{i['water_quantity']} {i.get('unit', 'L')}, Date: {i['date']}"
            )
    
    if not soil_data and not irr_data:
        return {
            "status": "success",
            "data": {
                "overview": "No soil or irrigation data available yet. Add soil tests and irrigation records to get AI-powered insights.",
                "recommendations": [],
                "model": "local",
            },
        }
    
    prompt = (
        "You are an agricultural expert for Farm Assist. Analyze the REAL soil and irrigation data "
        "provided above. Provide a concise farmer-friendly summary covering:\n"
        "1. Overall soil and irrigation condition\n"
        "2. What looks good\n"
        "3. What needs attention\n"
        "4. Specific recommended actions\n"
        "5. Water management advice\n"
        "6. Crop-specific guidance where relevant\n\n"
        "Never invent values. If data is missing, say so. Keep it practical and actionable for farmers.\n\n"
        + "\n".join(context_lines)
    )
    
    try:
        ai_response = await chat_with_ai(prompt)
        ai_text = ai_response.get("response", "Analysis temporarily unavailable.")
        model = ai_response.get("model", "local")
    except Exception:
        ai_text = "AI analysis temporarily unavailable. Please try again later."
        model = "local"
    
    return {
        "status": "success",
        "data": {
            "overview": ai_text,
            "recommendations": [],
            "model": model,
            "context": {
                "farms": [f.farm_name for f in farm_objs],
                "plots": [p.plot_name for p in plots],
                "has_soil_data": len(soil_data) > 0,
                "has_irrigation_data": len(irr_data) > 0,
            },
        },
    }


@router.get("/soil-health-status", response_model=dict)
def get_soil_health_status(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Calculate overall soil health status based on latest readings."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    status_by_plot = {}
    
    for pid in plot_ids:
        latest = db.query(SoilRecord).filter(
            SoilRecord.plot_id == pid
        ).order_by(SoilRecord.test_date.desc()).first()
        
        if not latest:
            status_by_plot[pid] = {
                "status": "no_data",
                "label": "No Data",
                "message": "No soil test data available for this plot.",
            }
            continue
        
        # Simple health logic based on pH and moisture
        issues = []
        
        if latest.ph_level:
            if latest.ph_level < 5.5:
                issues.append("pH is too acidic")
            elif latest.ph_level > 7.5:
                issues.append("pH is too alkaline")
        
        if latest.moisture:
            if latest.moisture < 30:
                issues.append("Soil moisture is low")
            elif latest.moisture > 80:
                issues.append("Soil moisture is high")
        
        if latest.organic_matter and latest.organic_matter < 1.0:
            issues.append("Organic matter is low")
        
        if not issues:
            status = "healthy"
            label = "Healthy"
            message = "Soil parameters are within acceptable ranges."
        elif len(issues) == 1:
            status = "needs_attention"
            label = "Needs Attention"
            message = f"{issues[0]}."
        else:
            status = "critical"
            label = "Critical"
            message = ", ".join(issues) + "."
        
        plot = db.query(FarmPlot).get(pid)
        status_by_plot[pid] = {
            "status": status,
            "label": label,
            "message": message,
            "plot_name": plot.plot_name if plot else None,
            "last_tested": _stamp(latest.test_date),
        }
    
    return {
        "status": "success",
        "data": status_by_plot,
    }


@router.get("/irrigation-status", response_model=dict)
def get_irrigation_status(
    farm_id: Optional[str] = None,
    plot_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Determine irrigation status based on recent activity and soil moisture."""
    farm_objs, plots = _resolve_scope(db, current_user, farm_id, plot_id)
    plot_ids = [p.id for p in plots]
    
    status_by_plot = {}
    
    for pid in plot_ids:
        # Get latest soil moisture
        latest_soil = db.query(SoilRecord).filter(
            SoilRecord.plot_id == pid
        ).order_by(SoilRecord.test_date.desc()).first()
        
        # Get latest irrigation
        latest_irr = db.query(IrrigationRecord).filter(
            IrrigationRecord.plot_id == pid
        ).order_by(IrrigationRecord.irrigation_date.desc()).first()
        
        # Try to get live sensor data if available
        try:
            from app.routers.sensors import Sensor, SensorReading
        except ImportError:
            Sensor = None
            SensorReading = None
        sensor = db.query(Sensor).filter(
            Sensor.plot_id == pid,
            Sensor.sensor_type == "soil_moisture",
            Sensor.is_active == True
        ).first()
        
        live_moisture = None
        if sensor and sensor.last_reading:
            live_moisture = sensor.last_reading.get("value")
        
        # Determine status
        moisture_value = live_moisture or (latest_soil.moisture if latest_soil else None)
        
        if moisture_value is None:
            status = "data_unavailable"
            label = "Data Unavailable"
            message = "No soil moisture data available."
        elif moisture_value < 30:
            status = "water_needed"
            label = "Water Needed"
            message = "Soil moisture is below optimal levels."
        elif moisture_value < 50:
            status = "irrigation_recommended"
            label = "Irrigation Recommended"
            message = "Soil moisture is adequate but irrigation may be needed soon."
        else:
            status = "moisture_sufficient"
            label = "Moisture Sufficient"
            message = "Soil moisture is within optimal range."
        
        # Add last irrigation info
        last_irrigation_info = None
        if latest_irr:
            last_irrigation_info = {
                "date": _stamp(latest_irr.irrigation_date),
                "method": latest_irr.method,
                "duration_minutes": latest_irr.duration_minutes,
            }
        
        plot = db.query(FarmPlot).get(pid)
        status_by_plot[pid] = {
            "status": status,
            "label": label,
            "message": message,
            "plot_name": plot.plot_name if plot else None,
            "current_moisture": moisture_value,
            "moisture_source": "sensor" if live_moisture else "soil_test",
            "last_irrigation": last_irrigation_info,
        }
    
    return {
        "status": "success",
        "data": status_by_plot,
    }

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.models.farm import Farm, FarmPlot
from app.utils.auth import get_current_user, generate_id

router = APIRouter(prefix="/api/v1", tags=["Farms"])


class FarmCreateRequest(BaseModel):
    farm_name: str
    address: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    total_area: Optional[float] = None
    area_unit: Optional[str] = "Acres"
    soil_type: Optional[str] = None
    water_source: Optional[str] = None
    irrigation_method: Optional[str] = None
    farm_type: Optional[str] = None


class FarmUpdateRequest(BaseModel):
    farm_name: Optional[str] = None
    address: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    total_area: Optional[float] = None
    area_unit: Optional[str] = None
    soil_type: Optional[str] = None
    water_source: Optional[str] = None
    irrigation_method: Optional[str] = None
    farm_type: Optional[str] = None


class PlotCreateRequest(BaseModel):
    plot_name: str
    area: Optional[float] = None
    boundary_coordinates: Optional[dict] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    soil_type: Optional[str] = None


class PlotUpdateRequest(BaseModel):
    plot_name: Optional[str] = None
    area: Optional[float] = None
    boundary_coordinates: Optional[dict] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    soil_type: Optional[str] = None


def _farm_dict(farm: Farm) -> dict:
    return {
        "id": farm.id,
        "farm_id": farm.farm_id,
        "farm_name": farm.farm_name,
        "address": farm.address,
        "village": farm.village,
        "mandal": farm.mandal,
        "district": farm.district,
        "state": farm.state,
        "pincode": farm.pincode,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "total_area": farm.total_area,
        "area_unit": farm.area_unit,
        "soil_type": farm.soil_type,
        "water_source": farm.water_source,
        "irrigation_method": farm.irrigation_method,
        "farm_type": farm.farm_type,
        "created_at": str(farm.created_at) if farm.created_at else None,
    }


def _plot_dict(plot: FarmPlot) -> dict:
    return {
        "id": plot.id,
        "plot_id": plot.plot_id,
        "plot_name": plot.plot_name,
        "area": plot.area,
        "boundary_coordinates": plot.boundary_coordinates,
        "latitude": plot.latitude,
        "longitude": plot.longitude,
        "soil_type": plot.soil_type,
        "created_at": str(plot.created_at) if plot.created_at else None,
    }


@router.get("/farms", response_model=dict)
def list_farms(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farms = db.query(Farm).filter(Farm.user_id == current_user.id, Farm.is_active == True).all()
    return {
        "status": "success",
        "data": [_farm_dict(f) for f in farms],
    }


@router.post("/farms", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_farm(
    payload: FarmCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm_id = generate_id("FA-FARM", db, Farm)

    farm = Farm(
        farm_id=farm_id,
        user_id=current_user.id,
        farm_name=payload.farm_name,
        address=payload.address,
        village=payload.village,
        mandal=payload.mandal,
        district=payload.district,
        state=payload.state,
        pincode=payload.pincode,
        latitude=payload.latitude,
        longitude=payload.longitude,
        total_area=payload.total_area,
        area_unit=payload.area_unit,
        soil_type=payload.soil_type,
        water_source=payload.water_source,
        irrigation_method=payload.irrigation_method,
        farm_type=payload.farm_type,
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)

    return {
        "status": "success",
        "message": "Farm created successfully",
        "data": _farm_dict(farm),
    }


@router.get("/farms/{farm_id}", response_model=dict)
def get_farm(
    farm_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    plots = db.query(FarmPlot).filter(FarmPlot.farm_id == farm.id).all()

    farm_data = _farm_dict(farm)
    farm_data["plots"] = [_plot_dict(p) for p in plots]

    return {"status": "success", "data": farm_data}


@router.put("/farms/{farm_id}", response_model=dict)
def update_farm(
    farm_id: str,
    payload: FarmUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)

    db.commit()
    db.refresh(farm)

    return {
        "status": "success",
        "message": "Farm updated successfully",
        "data": _farm_dict(farm),
    }


@router.delete("/farms/{farm_id}", response_model=dict)
def delete_farm(
    farm_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    farm.is_active = False
    db.commit()

    return {"status": "success", "message": "Farm deleted successfully"}


@router.get("/farms/{farm_id}/plots", response_model=dict)
def list_plots(
    farm_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    plots = db.query(FarmPlot).filter(FarmPlot.farm_id == farm.id, FarmPlot.is_active == True).all()

    return {
        "status": "success",
        "data": [_plot_dict(p) for p in plots],
    }


@router.post("/farms/{farm_id}/plots", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_plot(
    farm_id: str,
    payload: PlotCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    plot_id = generate_id("FA-PLT", db, FarmPlot)

    plot = FarmPlot(
        plot_id=plot_id,
        farm_id=farm.id,
        plot_name=payload.plot_name,
        area=payload.area,
        boundary_coordinates=payload.boundary_coordinates,
        latitude=payload.latitude,
        longitude=payload.longitude,
        soil_type=payload.soil_type,
    )
    db.add(plot)
    db.commit()
    db.refresh(plot)

    return {
        "status": "success",
        "message": "Plot created successfully",
        "data": _plot_dict(plot),
    }


@router.put("/plots/{plot_id}", response_model=dict)
def update_plot(
    plot_id: str,
    payload: PlotUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plot = db.query(FarmPlot).filter(FarmPlot.plot_id == plot_id).first()
    if not plot:
        raise HTTPException(status_code=404, detail="Plot not found")

    farm = db.query(Farm).filter(Farm.id == plot.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized to modify this plot")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(plot, field, value)

    db.commit()
    db.refresh(plot)

    return {
        "status": "success",
        "message": "Plot updated successfully",
        "data": _plot_dict(plot),
    }


@router.delete("/plots/{plot_id}", response_model=dict)
def delete_plot(
    plot_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plot = db.query(FarmPlot).filter(FarmPlot.plot_id == plot_id).first()
    if not plot:
        raise HTTPException(status_code=404, detail="Plot not found")

    farm = db.query(Farm).filter(Farm.id == plot.farm_id, Farm.user_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=403, detail="Not authorized to modify this plot")

    plot.is_active = False
    db.commit()

    return {"status": "success", "message": "Plot deleted successfully"}

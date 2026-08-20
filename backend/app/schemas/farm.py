from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class FarmCreate(BaseModel):
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
    area_unit: Optional[str] = None
    soil_type: Optional[str] = None
    water_source: Optional[str] = None
    irrigation_method: Optional[str] = None
    farm_type: Optional[str] = None


class FarmUpdate(BaseModel):
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


class FarmResponse(BaseModel):
    id: str
    farm_id: Optional[str] = None
    user_id: str
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
    area_unit: Optional[str] = None
    soil_type: Optional[str] = None
    water_source: Optional[str] = None
    irrigation_method: Optional[str] = None
    farm_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlotCreate(BaseModel):
    plot_name: str
    area: Optional[float] = None
    boundary_coordinates: Optional[Any] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    soil_type: Optional[str] = None


class PlotUpdate(BaseModel):
    plot_name: Optional[str] = None
    area: Optional[float] = None
    boundary_coordinates: Optional[Any] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    soil_type: Optional[str] = None


class PlotResponse(BaseModel):
    id: str
    plot_id: Optional[str] = None
    farm_id: str
    plot_name: str
    area: Optional[float] = None
    boundary_coordinates: Optional[Any] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    soil_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FarmDocumentCreate(BaseModel):
    document_type: str
    document_name: Optional[str] = None
    file_url: Optional[str] = None


class FarmDocumentResponse(BaseModel):
    id: str
    document_id: Optional[str] = None
    farm_id: str
    document_type: str
    document_name: Optional[str] = None
    file_url: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    verification_status: Optional[str] = None

    class Config:
        from_attributes = True

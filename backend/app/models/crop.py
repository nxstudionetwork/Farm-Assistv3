from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Float, ForeignKey, Text, Boolean, JSON, Integer
)
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.models.farm import gen_uuid


class CropCategory(Base):
    """One node of the crop taxonomy.

    The hierarchy is expressed with plain ``domain`` / ``category`` /
    ``subcategory`` columns rather than a self-referencing parent, so a new
    level can be introduced without reshaping existing rows. Examples:

        Field Crops  / Cereals     / Rice
        Horticulture / Fruits      / Grapes
        Horticulture / Vegetables  / Tomato
    """

    __tablename__ = "crop_categories"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    #: machine key, unique and language independent (e.g. ``horticulture.fruits``)
    code = Column(String(120), unique=True, index=True, nullable=False)
    #: broad agricultural domain (Field Crops, Horticulture, Plantation, ...)
    domain = Column(String(80), nullable=True, index=True)
    #: group inside the domain (Cereals, Fruits, Vegetables, Spices, ...)
    category = Column(String(80), nullable=True, index=True)
    #: optional finer grouping inside the category
    subcategory = Column(String(80), nullable=True, index=True)
    display_name = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)
    icon = Column(String(60), nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    crops = relationship("Crop", back_populates="category_ref")


class CultivationMethod(Base):
    """How a crop is grown, kept separate from the crop itself.

    This is what stops the catalog growing duplicates such as
    "Tomato Greenhouse" and "Tomato Field": the same Crop row is reused and
    only the method recorded on the crop cycle changes.
    """

    __tablename__ = "cultivation_methods"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    code = Column(String(60), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    #: False for hydroponics, where soil based guidance must not apply.
    is_soil_based = Column(Boolean, default=True)
    #: True for greenhouse/polyhouse/shade-net style protected structures.
    is_protected = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cycles = relationship("CropCycle", back_populates="cultivation_method")


class CropVariety(Base):
    """A variety of a crop.

    Kept as its own table so a crop is never duplicated per variety. The
    legacy free-text ``Crop.variety`` column is still readable and is
    migrated into this table, so existing records keep working.
    """

    __tablename__ = "crop_varieties"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    local_name = Column(String(150), nullable=True)
    is_hybrid = Column(Boolean, default=False)
    duration_days = Column(Float, nullable=True)
    #: True when the farmer typed this in rather than picking a known variety.
    is_custom = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    crop = relationship("Crop", back_populates="varieties")
    cycles = relationship("CropCycle", back_populates="variety")


class Crop(Base):
    __tablename__ = "crops"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    crop_id = Column(String(20), unique=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    #: Legacy free-text variety. Retained for backward compatibility and
    #: mirrored into :class:`CropVariety` by the migration.
    variety = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    season = Column(String(50), nullable=True)
    growth_duration_days = Column(Float, nullable=True)

    # --- scalable taxonomy -------------------------------------------------
    domain = Column(String(80), nullable=True, index=True)
    category_id = Column(String(36), ForeignKey("crop_categories.id"), nullable=True)
    subcategory = Column(String(80), nullable=True, index=True)

    # --- descriptive reference data ----------------------------------------
    scientific_name = Column(String(150), nullable=True)
    #: {"te": "...", "hi": "..."} - names per language, never separate crops
    local_names = Column(JSON, nullable=True)
    #: annual / perennial / biennial / seasonal / multi_year
    life_cycle_type = Column(String(30), nullable=True, index=True)
    suitable_seasons = Column(String(120), nullable=True)
    suitable_climate = Column(String(160), nullable=True)
    suitable_soil_types = Column(String(160), nullable=True)
    water_requirement = Column(String(80), nullable=True)
    harvest_type = Column(String(80), nullable=True)
    production_unit = Column(String(30), nullable=True)
    storage_notes = Column(String(255), nullable=True)
    market_type = Column(String(80), nullable=True)
    #: Ordered stage names for this crop, e.g. grapes' dormancy -> pruning.
    lifecycle_stages = Column(JSON, nullable=True)
    #: Cultivation method codes this crop supports, e.g.
    #: ["open_field", "soil", "protected", "hydroponic"]. Derived by the catalog
    #: seeder so the UI can filter by environment without a second crop list.
    suitable_cultivation_methods = Column(JSON, nullable=True)
    #: Nutrient solution targets for soilless culture, e.g.
    #: {"ph": [5.5, 6.5], "ec": [1.2, 2.0], "days": 40, "group": "Leafy"}.
    #: Lives on the crop so hydroponics reads its targets from the same catalog
    #: as every other module instead of keeping a parallel hardcoded crop list.
    hydroponic_targets = Column(JSON, nullable=True)

    # --- catalog bookkeeping ------------------------------------------------
    #: True for the shared reference catalog, False for farmer-created crops.
    is_catalog = Column(Boolean, default=False, index=True)
    is_archived = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    category_ref = relationship("CropCategory", back_populates="crops")
    varieties = relationship(
        "CropVariety", back_populates="crop", cascade="all, delete-orphan"
    )
    crop_cycles = relationship("CropCycle", back_populates="crop")


class CropCycle(Base):
    __tablename__ = "crop_cycles"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    cycle_id = Column(String(20), unique=True, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=False)
    sowing_date = Column(String(10), nullable=True)
    expected_harvest_date = Column(String(10), nullable=True)
    actual_harvest_date = Column(String(10), nullable=True)
    current_stage = Column(String(50), nullable=True)
    seed_quantity = Column(Float, nullable=True)
    seed_unit = Column(String(20), nullable=True)
    fertilizer_usage = Column(Text, nullable=True)
    pesticide_usage = Column(Text, nullable=True)
    irrigation_schedule = Column(Text, nullable=True)
    yield_quantity = Column(Float, nullable=True)
    yield_unit = Column(String(20), nullable=True)
    revenue = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- variety and cultivation method ------------------------------------
    variety_id = Column(String(36), ForeignKey("crop_varieties.id"), nullable=True)
    cultivation_method_id = Column(
        String(36), ForeignKey("cultivation_methods.id"), nullable=True
    )
    #: greenhouse / polyhouse / shade_net / net_house / none
    protected_structure = Column(String(40), nullable=True)
    planting_material = Column(String(120), nullable=True)

    farm = relationship("Farm", back_populates="crop_cycles")
    plot = relationship("FarmPlot", back_populates="crop_cycles")
    crop = relationship("Crop", back_populates="crop_cycles")
    variety = relationship("CropVariety", back_populates="cycles")
    cultivation_method = relationship("CultivationMethod", back_populates="cycles")
    tasks = relationship("CropTask", back_populates="crop_cycle", cascade="all, delete-orphan")


class CropTask(Base):
    __tablename__ = "crop_tasks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    task_id = Column(String(20), unique=True, index=True)
    crop_cycle_id = Column(String(36), ForeignKey("crop_cycles.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    due_date = Column(String(10), nullable=True)
    due_time = Column(String(10), nullable=True)
    status = Column(String(20), default="pending")
    priority = Column(String(20), default="medium")
    source = Column(String(30), nullable=True)
    growth_stage = Column(String(50), nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    crop_cycle = relationship("CropCycle", back_populates="tasks")


class FarmJournal(Base):
    __tablename__ = "farm_journal"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    activity = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    entry_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class SoilRecord(Base):
    __tablename__ = "soil_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=False)
    ph_level = Column(Float, nullable=True)
    nitrogen = Column(Float, nullable=True)
    phosphorus = Column(Float, nullable=True)
    potassium = Column(Float, nullable=True)
    organic_matter = Column(Float, nullable=True)
    moisture = Column(Float, nullable=True)
    soil_type = Column(String(50), nullable=True)
    test_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)


class IrrigationRecord(Base):
    __tablename__ = "irrigation_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=False)
    method = Column(String(50), nullable=True)
    duration_minutes = Column(Float, nullable=True)
    water_quantity = Column(Float, nullable=True)
    water_unit = Column(String(20), nullable=True)
    irrigation_date = Column(DateTime, default=datetime.utcnow)


class CropHealthCheck(Base):
    __tablename__ = "crop_health_checks"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    check_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    crop_cycle_id = Column(String(36), ForeignKey("crop_cycles.id"), nullable=True)
    crop_id = Column(String(36), ForeignKey("crops.id"), nullable=True)
    stage = Column(String(50), nullable=True)
    observations = Column(Text, nullable=True)
    symptom_codes = Column(JSON, nullable=True)
    possible_concern = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    follow_up = Column(Text, nullable=True)
    health_status = Column(String(30), default="normal")
    photo_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Float, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.farm import gen_uuid


class MonitoringAlert(Base):
    __tablename__ = "monitoring_alerts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    alert_id = Column(String(20), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    sensor_id = Column(String(36), ForeignKey("sensors.id"), nullable=True)
    alert_type = Column(String(50), nullable=False)  # below_threshold|above_threshold|offline|disconnected|manual
    metric = Column(String(50), nullable=True)
    message = Column(Text, nullable=False)
    severity = Column(String(20), default="warning")  # info|warning|critical
    status = Column(String(20), default="active")    # active|acknowledged|resolved
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    user = relationship("User")
    farm = relationship("Farm")
    plot = relationship("FarmPlot")
    sensor = relationship("Sensor")


class MonitoringThreshold(Base):
    __tablename__ = "monitoring_thresholds"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=False)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    metric = Column(String(50), nullable=False)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    farm = relationship("Farm")
    plot = relationship("FarmPlot")
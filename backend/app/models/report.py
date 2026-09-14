from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from app.database.base import Base
from app.models.farm import gen_uuid


class FarmReport(Base):
    """Generated farm analytics report owned by a single farmer."""

    __tablename__ = "farm_reports"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    report_id = Column(String(30), unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    farm_id = Column(String(36), ForeignKey("farms.id"), nullable=True)
    farm_name = Column(String(200), nullable=True)
    plot_id = Column(String(36), ForeignKey("farm_plots.id"), nullable=True)
    plot_name = Column(String(200), nullable=True)
    report_type = Column(String(50), nullable=False)
    title = Column(String(250), nullable=True)
    date_from = Column(String(10), nullable=True)
    date_to = Column(String(10), nullable=True)
    summary = Column(Text, nullable=True)
    data_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
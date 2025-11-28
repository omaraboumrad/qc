"""
SQLAlchemy database models for dynamic cluster and device management.
"""
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from datetime import datetime
from typing import Optional

Base = declarative_base()


class Cluster(Base):
    """
    Represents a logical group of devices.
    Multiple clusters can be active simultaneously.
    """
    __tablename__ = 'clusters'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    active = Column(Boolean, default=False, index=True)  # Multiple clusters can be active
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    devices = relationship('Device', back_populates='cluster', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Cluster(id={self.id}, name='{self.name}', active={self.active})>"


class Device(Base):
    """
    Represents an individual device (client container) within a cluster.
    Each device gets its own Docker network and router interface.
    """
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    device_type = Column(String(50))  # e.g., "pc", "mobile", "server"

    # Network Configuration (assigned when device is created)
    network_subnet = Column(String(20), nullable=False)      # e.g., "10.1.0.0/24"
    network_name = Column(String(100), unique=True, nullable=False)  # e.g., "qc_net_computers_laptop1"
    container_name = Column(String(100), unique=True, nullable=False)  # e.g., "qc_computers_laptop1"
    ip_address = Column(String(20), nullable=False)          # e.g., "10.1.0.10"
    router_ip = Column(String(20), nullable=False)           # e.g., "10.1.0.254"

    # Router Interface (dynamically assigned during sync when container is created)
    interface_name = Column(String(20))  # e.g., "eth1", "eth5" - assigned by router
    ifb_device = Column(String(20))      # e.g., "ifb1", "ifb5" - for upstream shaping

    # Container Status
    status = Column(String(20), default='stopped', index=True)  # stopped, starting, running, stopping, error
    error_message = Column(Text)
    last_synced_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship('Cluster', back_populates='devices')
    traffic_rules = relationship('TrafficRule', back_populates='device', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Device(id={self.id}, name='{self.name}', cluster_id={self.cluster_id}, status='{self.status}')>"


class TrafficRule(Base):
    """
    Stores traffic shaping rules for a device.
    Rules are preserved across container restarts.
    """
    __tablename__ = 'traffic_rules'

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(Integer, ForeignKey('devices.id', ondelete='CASCADE'), nullable=False, index=True)

    # Bidirectional Traffic Shaping
    downstream_rate = Column(String(20))  # e.g., "20mbit" (router → device guaranteed rate)
    downstream_ceil = Column(String(20))  # e.g., "50mbit" (router → device maximum)
    upstream_rate = Column(String(20))    # e.g., "10mbit" (device → router guaranteed rate)
    upstream_ceil = Column(String(20))    # e.g., "30mbit" (device → router maximum)

    # Metadata
    active = Column(Boolean, default=True, index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    device = relationship('Device', back_populates='traffic_rules')

    def __repr__(self):
        return f"<TrafficRule(id={self.id}, device_id={self.device_id}, down={self.downstream_rate}/{self.downstream_ceil}, up={self.upstream_rate}/{self.upstream_ceil})>"


# Database initialization and session management

def init_db(database_url: str = "sqlite:///./qc.db", echo: bool = False):
    """
    Initialize the database and create all tables.

    Args:
        database_url: SQLAlchemy database URL (default: SQLite in current directory)
        echo: If True, log all SQL statements (useful for debugging)

    Returns:
        SQLAlchemy engine instance
    """
    engine = create_engine(database_url, echo=echo)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine) -> Session:
    """
    Create a new database session.

    Args:
        engine: SQLAlchemy engine instance

    Returns:
        SQLAlchemy Session instance
    """
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return SessionLocal()


def get_session_factory(engine):
    """
    Get a session factory for dependency injection.

    Args:
        engine: SQLAlchemy engine instance

    Returns:
        SessionLocal class that can create new sessions
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)

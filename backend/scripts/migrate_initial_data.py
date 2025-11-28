#!/usr/bin/env python3
"""
Initial data migration script.

This script creates the default cluster with the 4 original hardcoded devices
(pc1, pc2, mb1, mb2) to maintain backward compatibility.

Run this once after setting up the database schema.
"""
import sys
import os

# Add parent directory to path so we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.database import DatabaseService


def migrate():
    """
    Create default cluster with original 4 devices.
    """
    print("Starting initial data migration...")

    # Initialize database service
    db = DatabaseService(db_path="qc.db", echo=True)

    try:
        # Check if default cluster already exists
        existing_cluster = db.get_cluster_by_name("default-cluster")
        if existing_cluster:
            print(f"⚠️  Default cluster already exists (ID: {existing_cluster.id})")
            print("Migration aborted to prevent duplicates.")
            return

        # Create default cluster
        print("\n1. Creating default cluster...")
        default_cluster = db.create_cluster(
            name="default-cluster",
            description="Migrated from original hardcoded setup (pc1, pc2, mb1, mb2)",
            active=True  # Start as active
        )
        print(f"✅ Created cluster: {default_cluster.name} (ID: {default_cluster.id})")

        # Define 4 devices matching original docker-compose configuration
        devices_config = [
            {
                "name": "pc1",
                "device_type": "pc",
                "subnet": "10.1.0.0/24",
                "device_ip": "10.1.0.10",
                "router_ip": "10.1.0.254",
            },
            {
                "name": "pc2",
                "device_type": "pc",
                "subnet": "10.2.0.0/24",
                "device_ip": "10.2.0.10",
                "router_ip": "10.2.0.254",
            },
            {
                "name": "mb1",
                "device_type": "mobile",
                "subnet": "10.3.0.0/24",
                "device_ip": "10.3.0.10",
                "router_ip": "10.3.0.254",
            },
            {
                "name": "mb2",
                "device_type": "mobile",
                "subnet": "10.4.0.0/24",
                "device_ip": "10.4.0.10",
                "router_ip": "10.4.0.254",
            },
        ]

        print("\n2. Creating 4 devices...")
        for config in devices_config:
            network_config = {
                "subnet": config["subnet"],
                "network_name": f"net_{config['name']}",  # Match existing docker-compose network names
                "container_name": config["name"],  # Keep original names for compatibility
                "device_ip": config["device_ip"],
                "router_ip": config["router_ip"],
            }

            device = db.create_device(
                cluster_id=default_cluster.id,
                name=config["name"],
                device_type=config["device_type"],
                network_config=network_config
            )
            print(f"  ✅ Created device: {device.name} ({device.device_type}) - {device.ip_address}")

        print("\n✅ Migration complete!")
        print(f"\nCreated:")
        print(f"  - 1 cluster: '{default_cluster.name}' (active)")
        print(f"  - 4 devices: pc1, pc2, mb1, mb2")
        print(f"\nNext steps:")
        print(f"  1. The existing Docker containers (pc1-mb2) are still running")
        print(f"  2. Run a sync operation to update the database with container status")
        print(f"  3. You can now create new clusters and devices via the UI")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

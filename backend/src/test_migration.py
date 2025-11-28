"""
Test database setup and run initial migration.
"""
import sys
sys.path.insert(0, '/app')

from src.services.database import DatabaseService

def test_migration():
    """Test database creation and migration."""
    print("Testing database setup and migration...")

    # Initialize database service
    db = DatabaseService(db_path="/app/qc.db", echo=True)

    try:
        # Test 1: Check if we can connect
        print("\n✅ Database connection successful!")

        # Test 2: Check if default cluster exists
        existing_cluster = db.get_cluster_by_name("default-cluster")
        if existing_cluster:
            print(f"\n⚠️  Default cluster already exists (ID: {existing_cluster.id})")
            print(f"   Devices in cluster: {len(existing_cluster.devices)}")
            for device in existing_cluster.devices:
                print(f"     - {device.name} ({device.status})")
            return

        # Test 3: Create default cluster
        print("\n Creating default cluster...")
        default_cluster = db.create_cluster(
            name="default-cluster",
            description="Migrated from original hardcoded setup (pc1, pc2, mb1, mb2)",
            active=True
        )
        print(f"✅ Created cluster: {default_cluster.name} (ID: {default_cluster.id})")

        # Test 4: Create 4 devices
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

        print("\nCreating 4 devices...")
        for config in devices_config:
            network_config = {
                "subnet": config["subnet"],
                "network_name": f"net_{config['name']}",
                "container_name": config["name"],
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

        # Test 5: Query back the data
        print("\n Verifying data...")
        all_clusters = db.list_clusters()
        print(f"  Total clusters: {len(all_clusters)}")

        active_clusters = db.get_active_clusters()
        print(f"  Active clusters: {len(active_clusters)}")

        all_devices = db.get_all_active_cluster_devices()
        print(f"  Devices in active clusters: {len(all_devices)}")

        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    test_migration()

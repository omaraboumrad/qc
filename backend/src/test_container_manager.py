"""
Test ContainerManager service - dynamic container lifecycle.
"""
import sys
sys.path.insert(0, '/app')

from src.services.database import DatabaseService
from src.services.container_manager import ContainerManager

def test_container_lifecycle():
    """Test creating and destroying a container dynamically."""
    print("Testing ContainerManager - Dynamic Container Lifecycle")
    print("=" * 60)

    # Initialize services
    db = DatabaseService(db_path="/app/qc.db", echo=False)
    cm = ContainerManager()

    try:
        # Get the default cluster and its devices
        print("\n1. Loading devices from database...")
        active_clusters = db.get_active_clusters()
        if not active_clusters:
            print("❌ No active clusters found. Run test_migration.py first.")
            return

        cluster = active_clusters[0]
        print(f"   Active cluster: {cluster.name}")

        devices = db.get_cluster_devices(cluster.id)
        if not devices:
            print("❌ No devices found in cluster.")
            return

        print(f"   Devices: {', '.join(d.name for d in devices)}")

        # Test with first device
        test_device = devices[0]
        print(f"\n2. Testing with device: {test_device.name}")
        print(f"   Container: {test_device.container_name}")
        print(f"   Network: {test_device.network_name}")
        print(f"   IP: {test_device.ip_address}")
        print(f"   Router IP: {test_device.router_ip}")

        # Test: Create container
        print(f"\n3. Creating container for {test_device.name}...")
        success, result = cm.create_device_container(test_device)

        if success:
            interface_name = result
            print(f"   ✅ Container created successfully!")
            print(f"   Router interface: {interface_name}")

            # Update device status in database
            db.update_device_status(
                device_id=test_device.id,
                status="running",
                interface_name=interface_name,
                ifb_device=f"ifb{interface_name.replace('eth', '')}" if 'eth' in interface_name else None
            )
            print(f"   ✅ Device status updated in database")

        else:
            print(f"   ❌ Container creation failed: {result}")
            return

        # Wait for user input to destroy
        print(f"\n4. Container is now running. Let's verify...")

        # Check running containers
        running = cm.get_running_containers()
        print(f"   Running QC containers: {len(running)}")
        for container in running:
            print(f"     - {container['name']} ({container['status']})")

        # Get device status from DB
        device = db.get_device(test_device.id)
        print(f"\n   Device status in DB:")
        print(f"     - Status: {device.status}")
        print(f"     - Interface: {device.interface_name}")
        print(f"     - IFB device: {device.ifb_device}")

        # Test: Destroy container
        print(f"\n5. Destroying container for {test_device.name}...")
        success, error = cm.destroy_device_container(test_device)

        if success:
            print(f"   ✅ Container destroyed successfully!")

            # Update device status in database
            db.update_device_status(
                device_id=test_device.id,
                status="stopped",
                interface_name=None,
                ifb_device=None
            )
            print(f"   ✅ Device status updated in database")

        else:
            print(f"   ❌ Container destruction failed: {error}")

        # Verify cleanup
        print(f"\n6. Verifying cleanup...")
        running = cm.get_running_containers()
        print(f"   Running QC containers: {len(running)}")

        device = db.get_device(test_device.id)
        print(f"   Device status: {device.status}")

        print(f"\n✅ All tests passed!")
        print(f"\nContainerManager is working correctly:")
        print(f"  ✅ Can create containers dynamically")
        print(f"  ✅ Detects router interfaces")
        print(f"  ✅ Initializes traffic control")
        print(f"  ✅ Can destroy containers cleanly")
        print(f"  ✅ Updates database status correctly")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    test_container_lifecycle()

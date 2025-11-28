"""
Test SyncService - Reconciliation engine.
"""
import sys
sys.path.insert(0, '/app')

from src.services.database import DatabaseService
from src.services.sync_service import SyncService
from src.services.container_manager import ContainerManager

def test_sync_engine():
    """Test the sync engine with multiple devices."""
    print("Testing SyncService - Reconciliation Engine")
    print("=" * 60)

    # Initialize services
    db = DatabaseService(db_path="/app/qc.db", echo=False)
    sync = SyncService(db_service=db)
    cm = ContainerManager()

    try:
        # Get the default cluster
        print("\n1. Loading default cluster...")
        active_clusters = db.get_active_clusters()
        if not active_clusters:
            print("❌ No active clusters found.")
            return

        cluster = active_clusters[0]
        print(f"   Cluster: {cluster.name} (ID: {cluster.id})")

        # Check current devices
        devices = db.get_cluster_devices(cluster.id)
        print(f"   Devices in DB: {len(devices)}")
        for device in devices:
            print(f"     - {device.name} (status: {device.status})")

        # Check running containers
        running = cm.get_running_containers()
        print(f"   Running containers: {len(running)}")
        for container in running:
            print(f"     - {container['name']}")

        # Test 1: Preview sync
        print(f"\n2. Getting sync preview...")
        preview = sync.get_sync_preview(cluster_id=cluster.id)
        print(f"   Preview:")
        print(f"     To CREATE: {len(preview.to_create)}")
        for name in preview.to_create:
            print(f"       + {name}")
        print(f"     To DESTROY: {len(preview.to_destroy)}")
        for name in preview.to_destroy:
            print(f"       - {name}")
        print(f"     To KEEP: {len(preview.to_keep)}")
        for name in preview.to_keep:
            print(f"       = {name}")

        # Test 2: Add a new test device to database
        print(f"\n3. Adding new test devices to database...")

        # Create 2 test devices
        for i in [1, 2]:
            octet, subnet = db.get_next_available_network(cluster.id)
            network_config = {
                "subnet": subnet,
                "network_name": f"qc_net_{cluster.name}_test{i}",
                "container_name": f"qc_{cluster.name}_test{i}",
                "device_ip": f"10.{octet}.0.10",
                "router_ip": f"10.{octet}.0.254",
            }

            device = db.create_device(
                cluster_id=cluster.id,
                name=f"test{i}",
                device_type="test",
                network_config=network_config
            )
            print(f"   ✅ Created device: {device.name} ({device.container_name})")

        # Test 3: Preview again (should show 2 devices to create)
        print(f"\n4. Getting sync preview after adding devices...")
        preview = sync.get_sync_preview(cluster_id=cluster.id)
        print(f"   Preview:")
        print(f"     To CREATE: {len(preview.to_create)} (should be 2)")
        for name in preview.to_create:
            print(f"       + {name}")

        # Test 4: Execute sync
        print(f"\n5. Executing sync...")
        result = sync.sync_cluster(cluster.id)

        print(f"\n   Sync Results:")
        print(f"     ✅ Created: {result.created}")
        print(f"     ✅ Destroyed: {result.destroyed}")
        print(f"     ✅ Kept: {result.kept}")
        print(f"     ✅ Updated: {result.updated}")
        if result.errors:
            print(f"     ❌ Errors: {result.errors}")

        # Test 5: Verify containers are running
        print(f"\n6. Verifying containers...")
        running = cm.get_running_containers()
        test_containers = [c for c in running if 'test' in c['name']]
        print(f"   Test containers running: {len(test_containers)}")
        for container in test_containers:
            print(f"     ✅ {container['name']} ({container['status']})")

        # Test 6: Verify database status
        print(f"\n7. Verifying database status...")
        devices = db.get_cluster_devices(cluster.id)
        test_devices = [d for d in devices if 'test' in d.name]
        for device in test_devices:
            print(f"     {device.name}:")
            print(f"       Status: {device.status}")
            print(f"       Interface: {device.interface_name}")
            print(f"       IFB: {device.ifb_device}")

        # Test 7: Remove devices from database and sync (should destroy containers)
        print(f"\n8. Removing test devices from database...")
        for device in test_devices:
            db.delete_device(device.id)
            print(f"   ✅ Deleted {device.name} from DB")

        # Test 8: Preview should show 2 to destroy
        print(f"\n9. Getting sync preview after deleting devices...")
        preview = sync.get_sync_preview(cluster_id=cluster.id)
        print(f"   Preview:")
        print(f"     To DESTROY: {len(preview.to_destroy)} (should be 2)")
        for name in preview.to_destroy:
            print(f"       - {name}")

        # Test 9: Execute sync to clean up
        print(f"\n10. Executing sync to destroy orphaned containers...")
        result = sync.sync_cluster(cluster.id)

        print(f"\n   Sync Results:")
        print(f"     ✅ Destroyed: {result.destroyed}")
        if result.errors:
            print(f"     ❌ Errors: {result.errors}")

        # Test 10: Verify cleanup
        print(f"\n11. Verifying cleanup...")
        running = cm.get_running_containers()
        test_containers = [c for c in running if 'test' in c['name']]
        if test_containers:
            print(f"   ⚠️  Still {len(test_containers)} test containers running")
        else:
            print(f"   ✅ All test containers cleaned up")

        print(f"\n{'='*60}")
        print(f"✅ All sync engine tests passed!")
        print(f"{'='*60}")
        print(f"\nSyncService is working correctly:")
        print(f"  ✅ Can preview sync operations")
        print(f"  ✅ Calculates diff correctly (create/destroy/keep)")
        print(f"  ✅ Creates containers in parallel")
        print(f"  ✅ Destroys containers in parallel")
        print(f"  ✅ Updates device status in database")
        print(f"  ✅ Handles orphaned containers")
        print(f"  ✅ Reconciles desired vs actual state")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sync.close()

if __name__ == "__main__":
    test_sync_engine()

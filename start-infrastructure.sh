#!/bin/bash
# Helper script to start the network infrastructure
# Docker Compose manages networks, this script ensures proper initialization

set -e

echo "Starting QC Network Traffic Shaping Playground..."

# Stop and remove any existing containers and networks
echo "Cleaning up existing containers..."
docker-compose down 2>/dev/null || true

# Start infrastructure containers (router and clients)
echo "Starting infrastructure containers..."
docker-compose up -d router pc1 pc2 mb1 mb2

# Wait for router to be ready
echo "Waiting for router to initialize..."
sleep 2

# Reinitialize traffic control now that all interfaces are available
echo "Initializing traffic control on all interfaces..."
docker exec router /scripts/init_tc.sh

echo ""
echo "✓ Infrastructure started successfully!"
echo ""
echo "Container Status:"
docker ps --filter "name=router|pc1|pc2|mb1|mb2" --format "table {{.Names}}\t{{.Status}}\t{{.Networks}}"

echo ""
echo "Router Interfaces:"
docker exec router ip addr show | grep -E "^[0-9]+: (eth|lo)" || true

echo ""
echo "Traffic Control Status:"
docker exec router tc qdisc show

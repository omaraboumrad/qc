# QC - Network Traffic Shaping Playground

A Docker-based network traffic shaping playground for learning bandwidth limiting and Quality of Service (QoS) with real-time web monitoring.

## Quick Start

### Start Infrastructure

```bash
./start-infrastructure.sh
```

This will start:
- 1 router container with traffic shaping capabilities
- 4 client containers (pc1, pc2, mb1, mb2)
- 5 isolated Docker networks

### Network Topology

```
    Router (10.x.0.254 on each network)
       ├── PC1 (10.1.0.10)
       ├── PC2 (10.2.0.10)
       ├── MB1 (10.3.0.10)
       └── MB2 (10.4.0.10)
```

### Test Traffic

```bash
# Basic connectivity test
docker exec pc1 ping -c 3 10.1.0.254

# Bandwidth test with iperf3
docker exec pc1 iperf3 -c 10.1.0.254 -t 10

# Multi-client test
docker exec pc1 iperf3 -c 10.1.0.254 -t 30 -P 4 &
docker exec pc2 iperf3 -c 10.2.0.254 -t 30 -P 4 &
```

### Check Traffic Shaping Stats

```bash
# View traffic control configuration
docker exec router tc qdisc show

# View detailed class statistics
docker exec router tc -s class show dev eth1
```

### Manual Traffic Shaping

```bash
# Change bandwidth limit for PC1 (eth1) to 10 Mbit
docker exec router tc class change dev eth1 parent 1:1 classid 1:30 htb rate 10mbit ceil 20mbit

# Test the limit
docker exec pc1 iperf3 -c 10.1.0.254 -t 10
# Should see bandwidth capped at ~10 Mbit/sec

# Reset to defaults
docker exec router /scripts/init_tc.sh
```

## Project Status

### ✅ Completed
- Phase 1: Infrastructure (Docker, networking, traffic shaping)
  - Router container with tc (HTB qdisc) and iptables
  - 4 client containers with iperf3
  - Custom Docker networks with static IPs
  - Traffic shaping scripts

### 🚧 In Progress
- Phase 2-3: Backend (FastAPI, metrics collection, SSE, InfluxDB)
- Phase 4: Rule Management API
- Phase 5: Frontend (React dashboard)
- Phase 6: Documentation

## Architecture

See [CLAUDE.md](CLAUDE.md) for detailed implementation plan and architecture.

## Default Traffic Shaping Configuration

Each client interface has 3 HTB classes:
- **High Priority (1:10)**: 50 Mbit rate, 100 Mbit ceiling
- **Medium Priority (1:20)**: 30 Mbit rate, 80 Mbit ceiling
- **Low Priority (1:30)**: 20 Mbit rate, 50 Mbit ceiling (default)

## Troubleshooting

### Containers won't start
```bash
# Clean up and restart
docker-compose down
./start-infrastructure.sh
```

### Check container logs
```bash
docker logs router
docker logs pc1
```

### Check traffic shaping is working
```bash
# Should show HTB qdisc on eth1-eth4
docker exec router tc qdisc show

# Should show 4 interfaces: eth0 (management) + eth1-4 (clients)
docker exec router ip addr show
```

## Development

For full implementation details, see the plan at `/Users/xterm/.claude/plans/ancient-stirring-rabbit.md`.

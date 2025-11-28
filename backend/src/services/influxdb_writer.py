import os
from typing import Optional
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from ..models.metrics import MetricsSnapshot


class InfluxDBWriter:
    """Write metrics to InfluxDB for historical storage"""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None
    ):
        self.url = url or os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
        self.token = token or os.getenv('INFLUXDB_TOKEN', 'qc-dev-token-change-in-production')
        self.org = org or os.getenv('INFLUXDB_ORG', 'qc')
        self.bucket = bucket or os.getenv('INFLUXDB_BUCKET', 'metrics')

        self.client = None
        self.write_api = None
        self._initialize()

    def _initialize(self):
        """Initialize InfluxDB client"""
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        except Exception as e:
            print(f"Warning: Failed to initialize InfluxDB: {e}")
            print("Metrics will not be persisted to InfluxDB")

    def write_metrics(self, metrics: MetricsSnapshot) -> bool:
        """
        Write metrics snapshot to InfluxDB

        Returns:
            True if successful, False otherwise
        """
        if not self.write_api:
            return False

        try:
            points = []

            # Write interface metrics
            for interface, stats in metrics.interfaces.items():
                # Bandwidth point
                point = Point("bandwidth") \
                    .tag("interface", interface) \
                    .tag("client", stats.client) \
                    .field("mbps", stats.bandwidth_mbps) \
                    .field("utilization", stats.utilization_percent) \
                    .time(int(metrics.timestamp * 1_000_000_000))
                points.append(point)

                # Packet stats point
                point = Point("packets") \
                    .tag("interface", interface) \
                    .tag("client", stats.client) \
                    .field("sent", stats.packets_sent) \
                    .field("dropped", stats.packets_dropped) \
                    .time(int(metrics.timestamp * 1_000_000_000))
                points.append(point)

                # Class-specific stats
                for class_id, class_stats in stats.classes.items():
                    point = Point("traffic_class") \
                        .tag("interface", interface) \
                        .tag("client", stats.client) \
                        .tag("class_id", class_id) \
                        .field("bytes", class_stats.bytes) \
                        .field("packets", class_stats.packets) \
                        .field("drops", class_stats.drops) \
                        .field("overlimits", class_stats.overlimits) \
                        .time(int(metrics.timestamp * 1_000_000_000))
                    points.append(point)

            # Write connection count
            point = Point("connections") \
                .field("active", len(metrics.connections)) \
                .time(int(metrics.timestamp * 1_000_000_000))
            points.append(point)

            # Write all points
            self.write_api.write(bucket=self.bucket, record=points)
            return True

        except Exception as e:
            print(f"Error writing to InfluxDB: {e}")
            return False

    def close(self):
        """Close InfluxDB connection"""
        if self.client:
            self.client.close()

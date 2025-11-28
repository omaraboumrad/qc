import docker
from typing import Tuple, Optional


class DockerExecutor:
    """Execute commands in Docker containers"""

    def __init__(self):
        self.client = docker.from_env()
        self._router_container = None

    def get_router(self):
        """Get router container (cached)"""
        if not self._router_container:
            try:
                self._router_container = self.client.containers.get("router")
            except docker.errors.NotFound:
                raise RuntimeError("Router container not found. Is it running?")
        return self._router_container

    def exec_command(self, container_name: str, command: str) -> Tuple[int, str]:
        """
        Execute command in container

        Returns:
            Tuple of (exit_code, output)
        """
        try:
            container = self.client.containers.get(container_name)
            result = container.exec_run(command)
            return result.exit_code, result.output.decode('utf-8')
        except docker.errors.NotFound:
            raise RuntimeError(f"Container '{container_name}' not found")
        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {e}")

    def exec_router(self, command: str) -> Tuple[int, str]:
        """Execute command in router container"""
        router = self.get_router()
        result = router.exec_run(command)
        return result.exit_code, result.output.decode('utf-8')

    def exec_client(self, client_name: str, command: str) -> Tuple[int, str]:
        """Execute command in a client container"""
        return self.exec_command(client_name, command)

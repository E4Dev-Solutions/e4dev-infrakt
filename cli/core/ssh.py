from __future__ import annotations

import io
from pathlib import Path

import paramiko

from cli.core.exceptions import SSHConnectionError


class SSHClient:
    """Paramiko-based SSH client wrapper for remote server operations."""

    def __init__(
        self,
        host: str,
        user: str = "root",
        port: int = 22,
        key_path: str | None = None,
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.key_path = key_path
        self._client: paramiko.SSHClient | None = None

    @classmethod
    def from_server(cls, srv: "Server") -> "SSHClient":
        """Construct an SSHClient from a Server model instance."""
        return cls(host=srv.host, user=srv.user, port=srv.port, key_path=srv.ssh_key_path)

    def connect(self) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "username": self.user,
        }
        if self.key_path:
            kwargs["key_filename"] = str(Path(self.key_path).expanduser())
        try:
            client.connect(**kwargs)
        except Exception as exc:
            raise SSHConnectionError(f"Failed to connect to {self.user}@{self.host}:{self.port}: {exc}") from exc
        self._client = client

    def _ensure_connected(self) -> paramiko.SSHClient:
        if self._client is None:
            self.connect()
        assert self._client is not None
        return self._client

    def run(self, command: str, timeout: int = 30) -> tuple[str, str, int]:
        """Execute a command and return (stdout, stderr, exit_code)."""
        client = self._ensure_connected()
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return stdout.read().decode(), stderr.read().decode(), exit_code
        except Exception as exc:
            raise SSHConnectionError(f"Command failed on {self.host}: {exc}") from exc

    def run_checked(self, command: str, timeout: int = 30) -> str:
        """Execute a command and return stdout. Raises on non-zero exit."""
        stdout, stderr, exit_code = self.run(command, timeout=timeout)
        if exit_code != 0:
            raise SSHConnectionError(
                f"Command exited with {exit_code} on {self.host}:\n{stderr.strip()}"
            )
        return stdout

    def upload(self, local_path: str, remote_path: str) -> None:
        client = self._ensure_connected()
        sftp = client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()

    def upload_string(self, content: str, remote_path: str) -> None:
        """Write string content directly to a remote file."""
        client = self._ensure_connected()
        sftp = client.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(content)
        finally:
            sftp.close()

    def download(self, remote_path: str, local_path: str) -> None:
        client = self._ensure_connected()
        sftp = client.open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()

    def read_remote_file(self, remote_path: str) -> str:
        """Read content of a remote file and return as string."""
        client = self._ensure_connected()
        sftp = client.open_sftp()
        try:
            with sftp.file(remote_path, "r") as f:
                return f.read().decode()
        finally:
            sftp.close()

    def test_connection(self) -> bool:
        try:
            self.connect()
            stdout, _, code = self.run("echo ok")
            return code == 0 and "ok" in stdout
        except SSHConnectionError:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> SSHClient:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

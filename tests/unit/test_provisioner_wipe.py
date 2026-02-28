"""Tests for server wipe functionality."""

from unittest.mock import MagicMock

from cli.core.provisioner import wipe_server


class TestWipeServer:
    def test_wipe_stops_containers_prunes_docker_and_removes_directory(self):
        ssh = MagicMock()
        ssh.run.return_value = ""
        ssh.run_checked.return_value = ""
        wipe_server(ssh)
        calls = [c[0][0] for c in ssh.run.call_args_list + ssh.run_checked.call_args_list]
        assert any("docker stop" in c for c in calls)
        assert any("docker system prune" in c for c in calls)
        assert any("rm -rf /opt/infrakt" in c for c in calls)

    def test_wipe_calls_on_step_callback(self):
        ssh = MagicMock()
        ssh.run.return_value = ""
        on_step = MagicMock()
        wipe_server(ssh, on_step=on_step)
        assert on_step.call_count >= 3

    def test_wipe_tolerates_no_containers(self):
        ssh = MagicMock()
        ssh.run.return_value = ""
        wipe_server(ssh)

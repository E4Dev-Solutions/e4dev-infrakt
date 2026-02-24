"""Tests for the SSHClient wrapper (cli/core/ssh.py) using mocked paramiko."""

from unittest.mock import MagicMock, patch

import pytest

from cli.core.exceptions import SSHConnectionError
from cli.core.ssh import SSHClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exec_side_effect(stdout_data=b"ok\n", stderr_data=b"", exit_code=0):
    """
    Return a side-effect function for paramiko SSHClient.exec_command that
    simulates a remote command execution with the given outputs.
    """
    def _exec(command, timeout=None):
        mock_channel = MagicMock()
        mock_channel.recv_exit_status.return_value = exit_code

        mock_stdout = MagicMock()
        mock_stdout.channel = mock_channel
        mock_stdout.read.return_value = stdout_data

        mock_stderr = MagicMock()
        mock_stderr.read.return_value = stderr_data

        return MagicMock(), mock_stdout, mock_stderr

    return _exec


def _patched_client(exec_side_effect=None, connect_error=None):
    """
    Return a context manager that patches paramiko.SSHClient and yields
    a MagicMock instance pre-wired with exec_command behaviour.
    """
    mock_instance = MagicMock()
    if connect_error is not None:
        mock_instance.connect.side_effect = connect_error
    if exec_side_effect is not None:
        mock_instance.exec_command.side_effect = exec_side_effect

    patcher = patch("cli.core.ssh.paramiko.SSHClient", return_value=mock_instance)
    return patcher, mock_instance


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

class TestConnect:
    def test_connect_calls_paramiko_with_host_user_port(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1", user="admin", port=22)
            client.connect()

        mock_instance.connect.assert_called_once_with(
            hostname="10.0.0.1", port=22, username="admin"
        )

    def test_connect_passes_key_filename_when_key_path_given(self, tmp_path):
        key_file = tmp_path / "id_rsa"
        key_file.touch()
        patcher, mock_instance = _patched_client()

        with patcher:
            client = SSHClient(host="10.0.0.1", user="root", key_path=str(key_file))
            client.connect()

        call_kwargs = mock_instance.connect.call_args[1]
        assert "key_filename" in call_kwargs
        assert str(key_file) in call_kwargs["key_filename"]

    def test_connect_sets_auto_add_policy(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()

        mock_instance.set_missing_host_key_policy.assert_called_once()

    def test_connect_raises_ssh_connection_error_on_failure(self):
        patcher, mock_instance = _patched_client(connect_error=Exception("Connection refused"))
        with patcher:
            client = SSHClient(host="10.0.0.1")
            with pytest.raises(SSHConnectionError, match="Failed to connect"):
                client.connect()

    def test_connect_stores_client_after_successful_connection(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1")
            assert client._client is None
            client.connect()
            assert client._client is mock_instance


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

class TestRun:
    def test_run_returns_stdout_stderr_exit_code_tuple(self):
        ef = _make_exec_side_effect(stdout_data=b"hello world\n", stderr_data=b"", exit_code=0)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            stdout, stderr, code = client.run("echo hello world")

        assert stdout == "hello world\n"
        assert stderr == ""
        assert code == 0

    def test_run_returns_nonzero_exit_code_on_failure(self):
        ef = _make_exec_side_effect(stdout_data=b"", stderr_data=b"not found\n", exit_code=127)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            stdout, stderr, code = client.run("bad-command")

        assert code == 127
        assert "not found" in stderr

    def test_run_auto_connects_when_not_yet_connected(self):
        ef = _make_exec_side_effect()
        patcher, mock_instance = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            # Do NOT call connect() — run() should call it automatically
            client.run("echo ok")

        mock_instance.connect.assert_called_once()

    def test_run_uses_provided_timeout(self):
        patcher, mock_instance = _patched_client()
        # Wire exec_command to return a valid structure even without a specific side effect
        mock_channel = MagicMock()
        mock_channel.recv_exit_status.return_value = 0
        mock_stdout = MagicMock()
        mock_stdout.channel = mock_channel
        mock_stdout.read.return_value = b""
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        mock_instance.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            client.run("sleep 5", timeout=60)

        mock_instance.exec_command.assert_called_once_with("sleep 5", timeout=60)

    def test_run_raises_ssh_connection_error_when_exec_fails(self):
        patcher, mock_instance = _patched_client()
        mock_instance.exec_command.side_effect = Exception("socket closed")
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            with pytest.raises(SSHConnectionError, match="Command failed"):
                client.run("anything")


# ---------------------------------------------------------------------------
# run_checked
# ---------------------------------------------------------------------------

class TestRunChecked:
    def test_run_checked_returns_stdout_on_success(self):
        ef = _make_exec_side_effect(stdout_data=b"result\n", exit_code=0)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            output = client.run_checked("ls /")

        assert output == "result\n"

    def test_run_checked_raises_ssh_connection_error_on_nonzero_exit(self):
        ef = _make_exec_side_effect(
            stdout_data=b"", stderr_data=b"permission denied\n", exit_code=1
        )
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            with pytest.raises(SSHConnectionError, match="Command exited with 1"):
                client.run_checked("restricted-command")

    def test_run_checked_error_message_includes_stderr(self):
        ef = _make_exec_side_effect(stderr_data=b"access denied", exit_code=2)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            with pytest.raises(SSHConnectionError, match="access denied"):
                client.run_checked("fail-cmd")


# ---------------------------------------------------------------------------
# upload_string
# ---------------------------------------------------------------------------

class TestUploadString:
    def test_upload_string_writes_content_to_remote_path(self):
        patcher, mock_instance = _patched_client()
        mock_sftp = MagicMock()
        mock_remote_file = MagicMock()
        mock_sftp.file.return_value.__enter__ = MagicMock(return_value=mock_remote_file)
        mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
        mock_instance.open_sftp.return_value = mock_sftp

        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            client.upload_string("MY_VAR=secret\n", "/app/.env")

        mock_sftp.file.assert_called_once_with("/app/.env", "w")

    def test_upload_string_closes_sftp_after_write(self):
        patcher, mock_instance = _patched_client()
        mock_sftp = MagicMock()
        mock_sftp.file.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
        mock_instance.open_sftp.return_value = mock_sftp

        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            client.upload_string("content", "/remote/file")

        mock_sftp.close.assert_called_once()

    def test_upload_string_auto_connects_when_not_connected(self):
        patcher, mock_instance = _patched_client()
        mock_sftp = MagicMock()
        mock_sftp.file.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_sftp.file.return_value.__exit__ = MagicMock(return_value=False)
        mock_instance.open_sftp.return_value = mock_sftp

        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.upload_string("data", "/tmp/f")

        mock_instance.connect.assert_called_once()


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

class TestTestConnection:
    def test_test_connection_returns_true_when_echo_succeeds(self):
        ef = _make_exec_side_effect(stdout_data=b"ok\n", exit_code=0)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            result = client.test_connection()

        assert result is True

    def test_test_connection_returns_false_when_connect_raises(self):
        patcher, _ = _patched_client(connect_error=Exception("refused"))
        with patcher:
            client = SSHClient(host="10.0.0.1")
            result = client.test_connection()

        assert result is False

    def test_test_connection_returns_false_when_echo_exits_nonzero(self):
        ef = _make_exec_side_effect(stdout_data=b"", exit_code=1)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            result = client.test_connection()

        assert result is False

    def test_test_connection_returns_false_when_ok_not_in_stdout(self):
        ef = _make_exec_side_effect(stdout_data=b"something_else\n", exit_code=0)
        patcher, _ = _patched_client(exec_side_effect=ef)
        with patcher:
            client = SSHClient(host="10.0.0.1")
            result = client.test_connection()

        assert result is False


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

class TestClose:
    def test_close_calls_paramiko_close_and_clears_client(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1")
            client.connect()
            client.close()

        mock_instance.close.assert_called_once()
        assert client._client is None

    def test_close_is_idempotent_when_not_connected(self):
        client = SSHClient(host="10.0.0.1")
        # Should not raise even when never connected
        client.close()
        assert client._client is None


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_connects_on_enter(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1")
            with client as ctx:
                assert ctx is client
                mock_instance.connect.assert_called_once()

    def test_context_manager_closes_on_exit(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1")
            with client:
                pass

        mock_instance.close.assert_called_once()
        assert client._client is None

    def test_context_manager_closes_even_when_exception_raised(self):
        patcher, mock_instance = _patched_client()
        with patcher:
            client = SSHClient(host="10.0.0.1")
            with pytest.raises(RuntimeError):
                with client:
                    raise RuntimeError("something went wrong")

        mock_instance.close.assert_called_once()

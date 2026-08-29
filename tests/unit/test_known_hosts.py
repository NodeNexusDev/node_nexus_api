"""Tests for FileKnownHostsManager."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.runtime.known_hosts import FileKnownHostsManager
from app.core.config import Settings
from app.core.exceptions import HostKeyFetchError


def _settings(path="/tmp/known_hosts", auto_add=True, timeout=10):
    s = MagicMock(spec=Settings)
    s.SSH_KNOWN_HOSTS_PATH = path
    s.SSH_KNOWN_HOSTS_AUTO_ADD = auto_add
    s.SSH_KNOWN_HOSTS_FETCH_TIMEOUT = timeout
    return s


class TestKnownHostsManager:
    def test_auto_add_enabled(self):
        m = FileKnownHostsManager(_settings(auto_add=False))
        assert m.auto_add_enabled is False
        m2 = FileKnownHostsManager(_settings(auto_add=True))
        assert m2.auto_add_enabled is True

    def test_host_key(self):
        m = FileKnownHostsManager(_settings())
        assert m._host_key("example.com", 22) == "example.com"
        assert m._host_key("example.com", 2222) == "[example.com]:2222"

    @pytest.mark.asyncio
    async def test_ensure_directory_create(self, tmp_path):
        p = tmp_path / "a" / "known_hosts"
        m = FileKnownHostsManager(_settings(path=str(p)))
        await m.ensure_directory()
        assert p.parent.exists()
        assert p.exists()

    @pytest.mark.asyncio
    async def test_ensure_directory_create_exists(self, tmp_path):
        p = tmp_path / "known_hosts"
        p.write_text("old")
        m = FileKnownHostsManager(_settings(path=str(p)))
        await m.ensure_directory()
        assert p.exists()

    @pytest.mark.asyncio
    async def test_ensure_directory_mkdir_failure(self):
        m = FileKnownHostsManager(_settings(path="/tmp/known_hosts"))
        with patch.object(Path, "mkdir", side_effect=OSError("fail")):
            with pytest.raises(
                HostKeyFetchError, match="Cannot create known_hosts directory"
            ):
                await m.ensure_directory()

    @pytest.mark.asyncio
    async def test_ensure_directory_touch_failure(self, tmp_path):
        p = tmp_path / "newdir" / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch.object(Path, "touch", side_effect=OSError("fail")):
            with pytest.raises(
                HostKeyFetchError, match="Cannot create known_hosts file"
            ):
                await m.ensure_directory()

    @pytest.mark.asyncio
    async def test_ensure_directory_chmod_ignore(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("x")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch.object(Path, "chmod", side_effect=OSError("ignore")):
            await m.ensure_directory()  # should not raise

    @pytest.mark.asyncio
    async def test_is_present_no_file(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        assert await m._is_present("h", 22) is False

    @pytest.mark.asyncio
    async def test_is_present_with_ssh_keygen_success(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("host ssh-rsa AAA\n")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keygen",
        ):
            mock_proc = AsyncMock()
            mock_proc.wait = AsyncMock(return_value=None)
            mock_proc.returncode = 0
            with patch(
                "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.wait_for",
                    return_value=None,
                ):
                    assert await m._is_present("h", 22) is True

    @pytest.mark.asyncio
    async def test_is_present_ssh_keygen_not_found_then_false(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("host ssh-rsa AAA\n")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keygen",
        ):
            mock_proc = AsyncMock()
            mock_proc.wait = AsyncMock(return_value=None)
            mock_proc.returncode = 1
            with patch(
                "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                return_value=mock_proc,
            ):
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.wait_for",
                    return_value=None,
                ):
                    assert await m._is_present("h", 22) is False

    @pytest.mark.asyncio
    async def test_is_present_timeout_fallback(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("myhost ssh-rsa AAA")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keygen",
        ):
            with patch(
                "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                side_effect=TimeoutError,
            ):
                assert await m._is_present("myhost", 22) is True

    @pytest.mark.asyncio
    async def test_is_present_fallback_substring(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("myhost ssh-rsa AAA")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch("app.adapters.runtime.known_hosts.shutil.which", return_value=None):
            assert await m._is_present("myhost", 22) is True
            assert await m._is_present("other", 22) is False

    @pytest.mark.asyncio
    async def test_is_present_read_error(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("x")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch("app.adapters.runtime.known_hosts.shutil.which", return_value=None):
            with patch.object(Path, "read_text", side_effect=OSError("fail")):
                assert await m._is_present("h", 22) is False

    @pytest.mark.asyncio
    async def test_ensure_host_auto_add_disabled(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p), auto_add=False))
        assert await m.ensure_host("h", 22) is False

    @pytest.mark.asyncio
    async def test_ensure_host_already_present(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("h ssh-rsa AAA")
        m = FileKnownHostsManager(_settings(path=str(p), auto_add=True))
        with patch.object(m, "_is_present", return_value=True):
            with patch.object(m, "ensure_directory", return_value=None):
                assert await m.ensure_host("h", 22) is False

    @pytest.mark.asyncio
    async def test_ensure_host_fetch(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p), auto_add=True))
        with patch.object(m, "ensure_directory", return_value=None):
            with patch.object(m, "_is_present", return_value=False):
                with patch.object(
                    m, "_fetch_and_append", return_value=True
                ) as mock_fetch:
                    assert await m.ensure_host("h", 22) is True
                    mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_host(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("host")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch.object(m, "ensure_directory", return_value=None):
            with patch(
                "app.adapters.runtime.known_hosts.shutil.which",
                return_value="/usr/bin/ssh-keygen",
            ):
                mock_proc = AsyncMock()
                mock_proc.wait = AsyncMock(return_value=None)
                mock_proc.returncode = 0
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    with patch(
                        "app.adapters.runtime.known_hosts.asyncio.wait_for",
                        return_value=None,
                    ):
                        with patch.object(
                            m, "_fetch_and_append", return_value=True
                        ) as mock_fetch:
                            assert await m.refresh_host("h", 22) is True
                            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_host_remove_failed(self, tmp_path):
        p = tmp_path / "kh"
        p.write_text("host")
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch.object(m, "ensure_directory", return_value=None):
            with patch(
                "app.adapters.runtime.known_hosts.shutil.which",
                return_value="/usr/bin/ssh-keygen",
            ):
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    side_effect=OSError("fail"),
                ):
                    with patch.object(m, "_fetch_and_append", return_value=True):
                        # remove fails but fetch still called
                        result = await m.refresh_host("h", 22)
                        assert result is True

    @pytest.mark.asyncio
    async def test_fetch_no_ssh_keyscan(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch("app.adapters.runtime.known_hosts.shutil.which", return_value=None):
            with pytest.raises(HostKeyFetchError, match="ssh-keyscan is not available"):
                await m._fetch_and_append("h", 22, force=False)

    @pytest.mark.asyncio
    async def test_fetch_already_present_under_lock(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keyscan",
        ):
            with patch.object(m, "_is_present", return_value=True):
                assert await m._fetch_and_append("h", 22, force=False) is False

    @pytest.mark.asyncio
    async def test_fetch_timeout(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p), timeout=1))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            side_effect=lambda x: (
                "/usr/bin/ssh-keyscan" if x == "ssh-keyscan" else None
            ),
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
                mock_proc.kill = MagicMock()
                mock_proc.wait = AsyncMock()
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    with patch(
                        "app.adapters.runtime.known_hosts.asyncio.wait_for",
                        side_effect=TimeoutError,
                    ):
                        with pytest.raises(HostKeyFetchError, match="timeout"):
                            await m._fetch_and_append("h", 22, force=True)

    @pytest.mark.asyncio
    async def test_fetch_non_zero_exit(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keyscan",
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
                mock_proc.returncode = 1
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    with patch(
                        "app.adapters.runtime.known_hosts.asyncio.wait_for",
                        return_value=(b"", b"error"),
                    ):
                        with pytest.raises(HostKeyFetchError, match="Cannot fetch"):
                            await m._fetch_and_append("h", 22, force=True)

    @pytest.mark.asyncio
    async def test_fetch_no_stdout(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keyscan",
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                mock_proc.returncode = 0
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    with patch(
                        "app.adapters.runtime.known_hosts.asyncio.wait_for",
                        return_value=(b"", b""),
                    ):
                        with pytest.raises(HostKeyFetchError, match="no host keys"):
                            await m._fetch_and_append("h", 22, force=True)

    @pytest.mark.asyncio
    async def test_fetch_no_lines(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            side_effect=lambda x: (
                "/usr/bin/ssh-keyscan" if x == "ssh-keyscan" else None
            ),
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(b"# comment\n", b""))
                mock_proc.returncode = 0
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    with patch(
                        "app.adapters.runtime.known_hosts.asyncio.wait_for",
                        return_value=(b"# comment\n", b""),
                    ):
                        with pytest.raises(HostKeyFetchError, match="No host keys"):
                            await m._fetch_and_append("h", 22, force=True)

    @pytest.mark.asyncio
    async def test_fetch_success_with_validation(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        fake_key = "example.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ==\n"
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keyscan",
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(fake_key.encode(), b""))
                mock_proc.returncode = 0
                # validation proc
                mock_vproc = AsyncMock()
                mock_vproc.communicate = AsyncMock(return_value=(b"", b""))
                mock_vproc.returncode = 0

                # need to mock create_subprocess_exec to return different based on args
                async def fake_exec(*args, **kwargs):
                    if args[0] == "ssh-keyscan":
                        return mock_proc
                    else:
                        return mock_vproc

                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    side_effect=fake_exec,
                ):
                    result = await m._fetch_and_append("example.com", 22, force=True)
                    assert result is True
                    assert p.read_text().endswith("\n")

    @pytest.mark.asyncio
    async def test_fetch_validation_failed(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        fake_key = "bad key\n"
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keyscan",
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(fake_key.encode(), b""))
                mock_proc.returncode = 0
                mock_vproc = AsyncMock()
                mock_vproc.communicate = AsyncMock(return_value=(b"", b"invalid"))
                mock_vproc.returncode = 1

                async def fake_exec(*args, **kwargs):
                    if args[0] == "ssh-keyscan":
                        return mock_proc
                    return mock_vproc

                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    side_effect=fake_exec,
                ):
                    with pytest.raises(HostKeyFetchError, match="invalid"):
                        await m._fetch_and_append("h", 22, force=True)

    @pytest.mark.asyncio
    async def test_fetch_write_readonly(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        fake_key = "h ssh-rsa AAA\n"
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            side_effect=lambda x: (
                "/usr/bin/ssh-keyscan" if x == "ssh-keyscan" else None
            ),
        ):
            with patch.object(m, "_is_present", return_value=False):
                mock_proc = AsyncMock()
                mock_proc.communicate = AsyncMock(return_value=(fake_key.encode(), b""))
                mock_proc.returncode = 0
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    return_value=mock_proc,
                ):
                    with patch.object(
                        Path, "open", side_effect=OSError(30, "Read-only file system")
                    ):
                        with pytest.raises(HostKeyFetchError, match="read-only"):
                            await m._fetch_and_append("h", 22, force=True)

    @pytest.mark.asyncio
    async def test_fetch_oserror(self, tmp_path):
        p = tmp_path / "kh"
        m = FileKnownHostsManager(_settings(path=str(p)))
        with patch(
            "app.adapters.runtime.known_hosts.shutil.which",
            return_value="/usr/bin/ssh-keyscan",
        ):
            with patch.object(m, "_is_present", return_value=False):
                with patch(
                    "app.adapters.runtime.known_hosts.asyncio.create_subprocess_exec",
                    side_effect=OSError("fail"),
                ):
                    with pytest.raises(HostKeyFetchError, match="ssh-keyscan failed"):
                        await m._fetch_and_append("h", 22, force=True)

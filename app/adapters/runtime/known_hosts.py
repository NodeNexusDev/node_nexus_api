"""File-based known_hosts manager with ssh-keyscan."""

import asyncio
import shutil
from pathlib import Path

import structlog

from app.core.config import Settings
from app.core.exceptions import HostKeyFetchError

logger = structlog.get_logger()
audit = structlog.get_logger("audit")


class FileKnownHostsManager:
    """Manage OpenSSH known_hosts via ssh-keyscan/ssh-keygen."""

    def __init__(self, settings: Settings) -> None:
        self._path = Path(settings.SSH_KNOWN_HOSTS_PATH)
        self._timeout = settings.SSH_KNOWN_HOSTS_FETCH_TIMEOUT
        self._auto_add = settings.SSH_KNOWN_HOSTS_AUTO_ADD
        self._lock = asyncio.Lock()

    @property
    def auto_add_enabled(self) -> bool:
        return self._auto_add

    async def ensure_directory(self) -> None:
        """Create parent directory and empty file if missing."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            msg = f"Cannot create known_hosts directory: {exc}"
            raise HostKeyFetchError(msg) from exc
        if not self._path.exists():
            try:
                self._path.touch(mode=0o644, exist_ok=True)
                self._path.chmod(0o644)
            except OSError as exc:
                msg = f"Cannot create known_hosts file: {exc}"
                raise HostKeyFetchError(msg) from exc
        else:
            try:
                self._path.chmod(0o644)
            except OSError:
                pass
        logger.debug("known_hosts.directory_ready", path=str(self._path))

    def _host_key(self, host: str, port: int) -> str:
        return f"[{host}]:{port}" if port != 22 else host

    async def _is_present(self, host: str, port: int) -> bool:
        if not self._path.is_file():
            return False
        key = self._host_key(host, port)
        # Use ssh-keygen -F to check; fallback to grep if binary missing
        if shutil.which("ssh-keygen"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ssh-keygen",
                    "-F",
                    key,
                    "-f",
                    str(self._path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), timeout=5)
                return proc.returncode == 0
            except (TimeoutError, OSError):
                pass
        # Fallback: simple substring search
        try:
            text = self._path.read_text(encoding="utf-8", errors="ignore")
            # Hashed entries can't be detected via grep
            return key in text
        except OSError:
            return False

    async def ensure_host(self, host: str, port: int) -> bool:
        """Ensure host key is in known_hosts, fetching via ssh-keyscan if needed."""
        if not self._auto_add:
            return False
        await self.ensure_directory()
        if await self._is_present(host, port):
            logger.debug("known_hosts.already_present", host=host, port=port)
            return False
        return await self._fetch_and_append(host, port, force=False)

    async def refresh_host(self, host: str, port: int) -> bool:
        """Force refresh: remove old entries then fetch new."""
        await self.ensure_directory()
        # Remove old entries via ssh-keygen -R if available
        key = self._host_key(host, port)
        if shutil.which("ssh-keygen") and self._path.is_file():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ssh-keygen",
                    "-R",
                    key,
                    "-f",
                    str(self._path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), timeout=5)
                logger.debug(
                    "known_hosts.removed_old",
                    host=host,
                    port=port,
                    rc=proc.returncode,
                )
            except (TimeoutError, OSError) as exc:
                logger.warning(
                    "known_hosts.remove_failed",
                    host=host,
                    port=port,
                    error=str(exc),
                )
        return await self._fetch_and_append(host, port, force=True)

    async def _fetch_and_append(self, host: str, port: int, *, force: bool) -> bool:
        if not shutil.which("ssh-keyscan"):
            audit.warning("known_hosts.ssh_keyscan_missing", host=host, port=port)
            raise HostKeyFetchError("ssh-keyscan is not available in the runtime image")
        # Double-check under lock to avoid races
        async with self._lock:
            if not force and await self._is_present(host, port):
                return False
            logger.info("known_hosts.fetch_start", host=host, port=port)
            # Run ssh-keyscan
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ssh-keyscan",
                    "-p",
                    str(port),
                    "-t",
                    "ed25519,rsa,ecdsa,ssh-rsa",
                    host,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=self._timeout
                    )
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    audit.warning("known_hosts.fetch_timeout", host=host, port=port)
                    raise HostKeyFetchError(f"ssh-keyscan timeout for {host}:{port}")
                if proc.returncode != 0 or not stdout:
                    raw = stderr.decode(errors="ignore").strip() if stderr else ""
                    msg = raw if raw else "no host keys received"
                    audit.warning(
                        "known_hosts.fetch_failed",
                        host=host,
                        port=port,
                        returncode=proc.returncode,
                        stderr=msg[:500],
                    )
                    raise HostKeyFetchError(
                        f"Cannot fetch host key for {host}:{port}: {msg[:200]}"
                    )
                text = stdout.decode(errors="ignore")
                # Basic validation: each line should contain host and keytype
                lines = [
                    ln
                    for ln in text.splitlines()
                    if ln.strip() and not ln.startswith("#")
                ]
                if not lines:
                    raise HostKeyFetchError(f"No host keys received for {host}:{port}")
                # Validate via ssh-keygen -l on tmp file if available
                if shutil.which("ssh-keygen"):
                    import tempfile

                    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
                        tmp.write(text)
                        tmp_path = tmp.name
                    try:
                        vproc = await asyncio.create_subprocess_exec(
                            "ssh-keygen",
                            "-l",
                            "-f",
                            tmp_path,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        _, verr = await asyncio.wait_for(vproc.communicate(), timeout=5)
                        if vproc.returncode != 0:
                            vmsg = verr.decode(errors="ignore").strip() if verr else ""
                            msg = vmsg if vmsg else "invalid host key"
                            raise HostKeyFetchError(
                                f"Fetched host key invalid for {host}:{port}: "
                                f"{msg[:200]}"
                            )
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)
                # Append atomically under lock (still inside)
                try:
                    with self._path.open("a", encoding="utf-8") as f:
                        if not text.endswith("\n"):
                            text += "\n"
                        f.write(text)
                    self._path.chmod(0o644)
                except OSError as exc:
                    if "Read-only" in str(exc) or exc.errno == 30:  # EROFS
                        msg = (
                            f"known_hosts is read-only ({self._path}); "
                            "mount it writable or use emptyDir for auto-add"
                        )
                        raise HostKeyFetchError(msg) from exc
                    raise HostKeyFetchError(f"Cannot write known_hosts: {exc}") from exc
                audit.info("known_hosts.added", host=host, port=port, lines=len(lines))
                logger.info("known_hosts.added", host=host, port=port, lines=len(lines))
                return True
            except HostKeyFetchError:
                raise
            except OSError as exc:
                msg = f"ssh-keyscan failed for {host}:{port}: {exc}"
                raise HostKeyFetchError(msg) from exc

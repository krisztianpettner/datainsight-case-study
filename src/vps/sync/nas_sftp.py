"""NAS transfer utility — SSH *exec* channel (SCP-style) over Tailscale.

Stream-through architecture: the VPS never stores PDFs on disk. Files are
streamed to the NAS through the SSH **exec** channel (`cat > tmp` → `mv`), NOT
the SFTP subsystem.

Why exec, not SFTP (S167, doc 09 §S143): the NAS SFTP service is a fragile
DSM toggle — a reboot/DSM-update can silently disable it (it caused a 17-day
silent DR-fail, doc 09 §S143). The exec channel works whenever SSH + the
`vpsync` shell work, which is the robust foundation we actually maintain. This
matches doc 09 line 139 ("vps_app SCP → NAS outbox"); the legacy code used the
SFTP subsystem, the real solution evolved to SCP/exec — this module now matches.

The public function names keep the historical `..._nas`/`NasSFTPError` spelling
for back-compat with existing callers (vps_app + the S167 D2 portal upload).

Thread-safety: each call opens its own SSHClient (no shared pool).
"""

import json
import logging
import re
import shlex
from pathlib import PurePosixPath
from typing import Optional

import paramiko

from vps.config import VpsSettings, get_vps_settings

logger = logging.getLogger(__name__)


class NasSFTPError(Exception):
    """Raised when a NAS transfer operation fails (name kept for back-compat)."""


def _sanitize_filename(name: str) -> str:
    """Strip any path component / traversal from a user-supplied filename.

    S167 D2 (DA-K2): the portal upload's filename comes from the HTTP
    Content-Disposition header and is attacker-controlled — a value like
    ``../other_client/outbox/x.pdf`` must NOT be able to escape the per-client
    NAS directory. Keep only the basename, drop leading dots, cap length.
    (Belt-and-braces: every remote path is also shlex.quote-d in the exec cmd.)
    """
    base = (name or "file.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    base = base.lstrip(".") or "file.pdf"
    return base[:200]


def _get_ssh_client(settings: Optional[VpsSettings] = None) -> paramiko.SSHClient:
    """Open a fresh SSH connection to the NAS via Tailscale. Caller closes it."""
    s = settings or get_vps_settings()
    timeout = getattr(s, "NAS_SFTP_TIMEOUT", 30)
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=s.NAS_HOST,
            port=s.NAS_PORT,
            username=s.NAS_USER,
            pkey=paramiko.Ed25519Key.from_private_key_file(s.NAS_SSH_KEY),
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return client
    except Exception as exc:
        raise NasSFTPError(f"NAS SSH connection failed: {exc}") from exc


def _run(client: paramiko.SSHClient, cmd: str, stdin_bytes: Optional[bytes] = None):
    """Run a remote command over the exec channel. Returns (exit, stdout, stderr)."""
    chan_stdin, chan_stdout, chan_stderr = client.exec_command(cmd, timeout=60)
    if stdin_bytes is not None:
        chan_stdin.write(stdin_bytes)
        chan_stdin.flush()
        chan_stdin.channel.shutdown_write()
    out = chan_stdout.read()
    err = chan_stderr.read()
    exit_status = chan_stdout.channel.recv_exit_status()
    return exit_status, out, err


def _upload_stream(content: bytes, remote_path: str, settings: Optional[VpsSettings]) -> str:
    """Atomic stream-write: mkdir -p parent, `cat > .tmp`, then `mv` into place."""
    s = settings or get_vps_settings()
    p = PurePosixPath(remote_path)
    parent = str(p.parent)
    tmp_path = f"{parent}/.tmp_{p.name}"
    client = _get_ssh_client(s)
    try:
        rc, _, err = _run(client, f"mkdir -p {shlex.quote(parent)}")
        if rc != 0:
            raise NasSFTPError(f"mkdir failed ({rc}): {err.decode(errors='replace')[:200]}")
        rc, _, err = _run(client, f"cat > {shlex.quote(tmp_path)}", stdin_bytes=content)
        if rc != 0:
            _run(client, f"rm -f {shlex.quote(tmp_path)}")
            raise NasSFTPError(f"write failed ({rc}): {err.decode(errors='replace')[:200]}")
        rc, _, err = _run(client, f"mv -f {shlex.quote(tmp_path)} {shlex.quote(remote_path)}")
        if rc != 0:
            _run(client, f"rm -f {shlex.quote(tmp_path)}")
            raise NasSFTPError(f"mv failed ({rc}): {err.decode(errors='replace')[:200]}")
        logger.info("Uploaded to NAS (exec): %s (%d bytes)", remote_path, len(content))
        return remote_path
    finally:
        client.close()


def upload_to_nas(
    content: bytes,
    client_id: int,
    job_id: str,
    original_filename: str,
    settings: Optional[VpsSettings] = None,
) -> str:
    """Upload a PDF directly to the NAS *outbox* (vps_app dispatch path)."""
    s = settings or get_vps_settings()
    safe_name = f"{job_id}_{_sanitize_filename(original_filename)}"
    remote_path = f"{s.NAS_OUTBOX_BASE}/{client_id}/outbox/{safe_name}"
    return _upload_stream(content, remote_path, s)


def upload_to_nas_staging(
    content: bytes,
    client_id: int,
    job_id: str,
    original_filename: str,
    settings: Optional[VpsSettings] = None,
) -> str:
    """Stream a PDF to the NAS *staging* area (S167 D2, portal 2-step upload).

    The portal upload is two-step (upload → review → commit). The PDF must NOT
    persist on the VPS disk (GDPR/no-cloud), so at upload time it streams to
    NAS ``{client_id}/staging/{job_id}_{name}``. The dispatch_watcher only
    watches ``outbox`` — a staged file is NOT processed until commit moves it
    (move_staging_to_outbox). Returns the staging remote path.
    """
    s = settings or get_vps_settings()
    safe_name = f"{job_id}_{_sanitize_filename(original_filename)}"
    remote_path = f"{s.NAS_OUTBOX_BASE}/{client_id}/staging/{safe_name}"
    return _upload_stream(content, remote_path, s)


def move_staging_to_outbox(
    staging_path: str,
    settings: Optional[VpsSettings] = None,
) -> str:
    """Move a staged PDF into the NAS outbox at commit (S167 D2).

    Takes the exact staging remote path (ClientBatchFile.stored_path). The move
    is a remote ``mv`` (atomic, no re-transfer). This is the dispatch-trigger:
    the PC dispatch_watcher only processes files under ``outbox``. Returns the
    outbox remote path.
    """
    s = settings or get_vps_settings()
    if "/staging/" not in staging_path:
        raise NasSFTPError(f"Not a staging path: {staging_path}")
    outbox_path = staging_path.replace("/staging/", "/outbox/", 1)
    outbox_dir = str(PurePosixPath(outbox_path).parent)
    client = _get_ssh_client(s)
    try:
        rc, _, err = _run(client, f"mkdir -p {shlex.quote(outbox_dir)}")
        if rc != 0:
            raise NasSFTPError(f"mkdir outbox failed ({rc}): {err.decode(errors='replace')[:200]}")
        rc, _, err = _run(
            client, f"mv -f {shlex.quote(staging_path)} {shlex.quote(outbox_path)}"
        )
        if rc != 0:
            raise NasSFTPError(f"staging→outbox mv failed ({rc}): {err.decode(errors='replace')[:200]}")
        logger.info("Moved staging→outbox (exec): %s", outbox_path)
        return outbox_path
    finally:
        client.close()


def check_inbox_for_result(
    job_id: str,
    client_id: int,
    settings: Optional[VpsSettings] = None,
) -> Optional[dict]:
    """Check the NAS inbox for a result JSON file. Returns dict or None."""
    s = settings or get_vps_settings()
    inbox_path = f"{s.NAS_INBOX_BASE}/{client_id}/inbox/{job_id}.json"
    client = _get_ssh_client(s)
    try:
        rc, out, _ = _run(client, f"cat {shlex.quote(inbox_path)} 2>/dev/null")
        if rc != 0 or not out:
            return None
        return json.loads(out)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Failed to parse inbox result %s: %s", inbox_path, exc)
        return None
    finally:
        client.close()


def remove_inbox_file(
    job_id: str,
    client_id: int,
    settings: Optional[VpsSettings] = None,
):
    """Remove a processed result JSON from the NAS inbox (GDPR cleanup)."""
    s = settings or get_vps_settings()
    inbox_path = f"{s.NAS_INBOX_BASE}/{client_id}/inbox/{job_id}.json"
    client = _get_ssh_client(s)
    try:
        _run(client, f"rm -f {shlex.quote(inbox_path)}")
        logger.info("Cleaned up inbox: %s", inbox_path)
    except Exception as exc:
        logger.warning("Failed to cleanup inbox %s: %s", inbox_path, exc)
    finally:
        client.close()


def verify_nas_file_exists(
    remote_path: str,
    settings: Optional[VpsSettings] = None,
) -> bool:
    """Check whether a file exists on the NAS via a remote ``test -f``."""
    s = settings or get_vps_settings()
    client = _get_ssh_client(s)
    try:
        rc, _, _ = _run(client, f"test -f {shlex.quote(remote_path)}")
        return rc == 0
    except Exception as exc:
        logger.warning("NAS exists-check failed for %s: %s", remote_path, exc)
        return False
    finally:
        client.close()


def fetch_file_bytes(
    remote_path: str,
    settings: Optional[VpsSettings] = None,
) -> bytes:
    """Read a NAS file's bytes over the exec channel (S173 D1 — accountant
    source-PDF view). Streamed RAM-only — the VPS NEVER writes the raw PDF to
    disk (not even /tmp); the bytes are returned to the caller and GC'd after
    the HTTP response. The caller MUST have already AUTHORIZED the path (K7);
    the path is ``shlex.quote``-d and ``..`` is rejected belt-and-braces.
    """
    if not remote_path or ".." in remote_path:
        raise NasSFTPError(f"refused suspicious NAS path: {remote_path!r}")
    s = settings or get_vps_settings()
    client = _get_ssh_client(s)
    try:
        rc, out, err = _run(client, f"cat {shlex.quote(remote_path)}")
        if rc != 0:
            raise NasSFTPError(f"NAS read failed ({rc}): {err.decode(errors='replace')[:200]}")
        return out
    finally:
        client.close()


_OUTBOX_REF_RE = re.compile(r"^[0-9]+/[a-f0-9-]+$")


def fetch_outbox_pdf_by_ref(ref: str, settings: Optional[VpsSettings] = None) -> bytes:
    """Fetch the retained source PDF from the NAS outbox by its PII-FREE reference.

    S175 §10/4 — the book-keeper D1 "Ver original" view. ``ref`` is
    ``{vps_client_id}/{job_id}``; the actual filename (PII) stays NAS-side and NEVER
    reaches portal_db. Globs ``{OUTBOX_BASE}/{client_id}/outbox`` for the single
    ``{job_id}_*`` file (the job_id charset makes the glob unambiguous) and streams it
    RAM-only (no /tmp, like fetch_file_bytes). The caller MUST have already AUTHORIZED
    access (K7 — the ref comes from a K7-resolved row, not user input).

    Error messages name ONLY the (PII-free) ref, NEVER the matched NAS path / stderr —
    the filename is PII and must not leak into logs or the HTTP response (DA-K7).
    """
    if not ref or not _OUTBOX_REF_RE.match(ref):
        raise NasSFTPError(f"refused malformed outbox ref: {ref!r}")
    client_id, job_id = ref.split("/", 1)
    s = settings or get_vps_settings()
    outbox_dir = f"{s.NAS_OUTBOX_BASE}/{client_id}/outbox"
    client = _get_ssh_client(s)
    try:
        # `find` does the globbing; the pattern AND the dir are shlex-quoted so the
        # shell can't expand them (OUTBOX_BASE config-safe — DA-K1). job_id is regex-clean.
        rc, out, _ = _run(
            client,
            f"find {shlex.quote(outbox_dir)} -maxdepth 1 -type f "
            f"-name {shlex.quote(job_id + '_*')} ! -name '*.done'",
        )
        if rc != 0:
            raise NasSFTPError(f"NAS outbox lookup failed ({rc}) for ref {ref!r}")
        # BUG-027 (S185): a feldolgozás-marker `.done` fájl is illeszkedett a globra →
        # 2 találat → "ambiguous" → 503 MINDEN feldolgozott fájlra. A find kizárja, és
        # védekezésül itt is szűrünk (más marker-kiterjesztés ellen a jövőben).
        matches = [
            ln for ln in out.decode(errors="replace").splitlines()
            if ln.strip() and not ln.strip().endswith(".done")
        ]
        if not matches:
            raise NasSFTPError(f"source PDF not found for ref {ref!r} (destroyed or never stored)")
        if len(matches) > 1:
            raise NasSFTPError(f"ambiguous source PDF for ref {ref!r}: {len(matches)} matches")
        target = matches[0]
        rc, content, _ = _run(client, f"cat {shlex.quote(target)}")
        if rc != 0:
            # Name only the ref — `target` / stderr carry the PII filename.
            raise NasSFTPError(f"NAS read failed ({rc}) for ref {ref!r}")
        return content
    finally:
        client.close()

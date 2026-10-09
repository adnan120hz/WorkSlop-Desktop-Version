"""Shared error classification for device backup/restore operations."""
import asyncio
import errno
import plistlib
import ssl

import pymobiledevice3.exceptions as pm3_exc

# Errnos that mean the *network/device channel* failed, as opposed to a
# local filesystem problem on this computer. A bare OSError is only a
# connection error when it carries one of these (or is a ConnectionError
# / TimeoutError subclass, handled by type below): a local
# FileNotFoundError (ENOENT), PermissionError (EACCES) or ENOSPC must
# never be retried as if the device had dropped (Audit 53b).
_NETWORK_ERRNOS = frozenset({
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ECONNREFUSED,
    errno.ETIMEDOUT,
    errno.EPIPE,
    errno.EHOSTUNREACH,
    errno.EHOSTDOWN,
    errno.ENETUNREACH,
    errno.ENETDOWN,
    errno.ENOTCONN,
    errno.ESHUTDOWN,
})

# Local-filesystem OSError subclasses: always fatal, never a device
# connection problem, no matter what the message text says.
_LOCAL_OS_ERRORS = (FileNotFoundError, PermissionError,
                    IsADirectoryError, NotADirectoryError)


def is_device_locked_error(exc: Exception) -> bool:
    """Check if an exception indicates the device is locked (ErrorCode 208)."""
    msg = str(exc)
    return "ErrorCode" in msg and ("208" in msg or "Device locked" in msg or "MBErrorDomain" in msg)


def is_connection_error(exc: Exception) -> bool:
    """Check if an exception is a transient connection failure worth retrying.

    Only genuine network/device-channel failures qualify (Audit 53b):
    pymobiledevice3's ConnectionTerminatedError, ConnectionError
    subclasses (reset/refused/aborted/broken pipe), timeouts, TLS drops,
    and OSErrors carrying a network errno. Local filesystem errors on
    this computer (missing file, permission denied, ...) and disk-full
    are fatal, not connection errors. Disk-full in particular must
    propagate immediately (Audit 53a): retrying it a dozen-plus times
    without cleanup just burns time on an unrecoverable condition.
    """
    if isinstance(exc, pm3_exc.NotEnoughDiskSpaceError):
        return False
    if isinstance(exc, _LOCAL_OS_ERRORS):
        return False
    if isinstance(exc, (
        pm3_exc.ConnectionTerminatedError,
        ConnectionError,
        asyncio.TimeoutError,
        TimeoutError,
    )):
        return True
    # ssl.SSLError subclasses OSError; a TLS drop on the device channel
    # is a connection failure, not a local file problem.
    if isinstance(exc, ssl.SSLError):
        return True
    if isinstance(exc, OSError):
        return exc.errno in _NETWORK_ERRNOS
    msg = str(exc).lower()
    return "connection" in msg or "incomplete" in msg or "terminated" in msg


def is_device_lock_required_error(exc: Exception) -> bool:
    """True when lockdown refused to start a service because the device is locked.

    Distinct from :func:`is_device_locked_error`, which sniffs the
    mobilebackup2 "ErrorCode 208" text. A *paired* lockdown session can be
    established while the device still sits at the lock screen, so
    ``StartService`` answers ``PasswordProtected`` even though nothing is
    actually wrong: the device just has to be unlocked. That makes it a
    wait-and-retry condition, not a failure.
    """
    if isinstance(exc, (pm3_exc.PasswordRequiredError, pm3_exc.PasscodeRequiredError)):
        return True
    msg = str(exc)
    return "PasswordProtected" in msg or "PasscodeRequired" in msg


def is_transient_restore_error(error) -> bool:
    """True for Phase 3 errors that mean 'device still booting, try again'."""
    name = type(error).__name__
    msg = str(error)
    # Audit 53a: disk-full is fatal, not transient. This used to return
    # True ("retry after cleanup"), so Phase 3 retried a full disk 18x
    # with no cleanup ever happening. Propagate the original error.
    if isinstance(error, pm3_exc.NotEnoughDiskSpaceError) \
            or "NotEnoughDiskSpace" in name:
        return False
    # Connection-class failures only (Audit 53b): is_connection_error
    # covers ConnectionTerminatedError, ConnectionError, timeouts and
    # TLS drops (ssl.SSLError), while a local OSError on this computer
    # (missing file, permission) stays fatal instead of burning retries.
    if is_connection_error(error):
        return True
    if "InvalidService" in name:
        return True
    # MBErrorDomain/1: SpringBoard not ready for a restore yet.
    if "SpringBoard" in msg and "ready for a restore" in msg:
        return True
    # A malformed plist over the restore channel. On a freshly-rebooted iOS 27
    # device this is almost always the mobilebackup2 tunnel being torn down or
    # truncated mid-handshake, not a broken backup — retrying on a fresh
    # service reconnects and completes the restore. Aborting on the first
    # occurrence strands the user right after Phase 2 wiped the device (the
    # exact data-loss route seen with "InvalidFileException in Phase 3").
    if isinstance(error, plistlib.InvalidFileException):
        return True
    if "parse_plist invalid data" in msg:
        return True
    return "start" in msg.lower() and "service" in msg.lower()

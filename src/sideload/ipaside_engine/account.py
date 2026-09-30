"""Developer-account inventory and housekeeping, for one Apple ID at a time.

What a free Apple ID will let you do is bounded by things you cannot see from the outside:
how many certificates it holds, which tool registered each, how many app identifiers are
registered, and which devices are on the team. Apple shows all of it on a website; iPASide
signs with the same account and so should show it too, and let it be tidied up.

Every function takes an ``email``, because iPASide can hold several signed-in Apple IDs and
each has its own team. Omitted, it means whichever is active. The lookups run inside
:func:`ipaside_engine.gsa.acting_as`, so asking about one account never disturbs another.

Two things here are easy to get wrong and worth stating plainly:

* **Certificates are shared ground.** Apple scopes its development-certificate limit per
  machine, not per account, so one team routinely holds iPASide's certificate alongside
  Xcode's on a Mac and SideStore's on a phone - verified holding all three at once.
  Revoking one stops every app *it* signed from launching, which may be a different tool's
  apps entirely. So each certificate is reported with who registered it.
* **Registered identifiers are not the weekly ceiling.** Apple allows about ten *new* app
  identifiers per rolling seven days. What a team currently holds is a different number:
  deleting identifiers frees the names, not the week's allowance. Reporting the two as one
  fraction reads as spare capacity that may already be spent.
"""

from __future__ import annotations

from typing import Any

from . import developer, gsa, provision

#: New app identifiers a free account may register per rolling seven days.
#:
#: A ceiling on *registrations*, not on how many may exist - see the module docstring.
WEEKLY_APP_ID_LIMIT = 10


def _certificate(cert: dict[str, Any], ours_serial: str | None) -> dict[str, Any]:
    """One certificate, annotated with who registered it and what it is for."""
    kind = cert.get("certificateType") or {}
    machine = cert.get("machineName")
    serial = cert.get("serialNumber")

    # Two ways of recognising our own, because either alone can be wrong: the cached
    # serial names the certificate this machine actually holds the key for, while the
    # machine name catches one iPASide issued on a machine whose cache has since gone.
    is_ours = serial == ours_serial or machine == provision.CERTIFICATE_MACHINE_NAME
    return {
        "serial": serial,
        "name": cert.get("name"),
        "machine": machine,
        "type": kind.get("name"),
        "type_id": kind.get("certificateTypeDisplayId"),
        "expires": cert.get("expirationDate"),
        "status": cert.get("status"),
        "ours": is_ours,
        # True only for the certificate this machine holds the private key for, which is
        # the one whose loss actually breaks the apps iPASide installed here.
        "in_use_here": serial is not None and serial == ours_serial,
    }


def overview(email: str | None = None) -> dict[str, Any]:
    """Everything iPASide can see about one Apple ID's developer account."""
    with gsa.acting_as(email):
        session = gsa.load_session()
        team = developer.list_teams()[0]
        team_id = team["teamId"]

        certificates = developer.list_certificates(team_id)
        app_ids = developer.list_app_ids(team_id)
        devices = developer.list_devices(team_id)

    # The cached bundle names the certificate this machine signs with; absent before the
    # account has ever provisioned, which is not an error.
    ours_serial: str | None = None
    try:
        with gsa.acting_as(email):
            bundle = provision.load_bundle()
        if bundle.get("team_id") == team_id:
            ours_serial = bundle.get("certificate_serial")
    except gsa.GsaError:
        pass

    return {
        "account": session.get("email") or email,
        "team": {
            "id": team_id,
            "name": team.get("name"),
            "type": team.get("type"),
        },
        "certificates": [_certificate(c, ours_serial) for c in certificates],
        "app_ids": [
            {
                "id": a.get("appIdId"),
                "identifier": a.get("identifier"),
                "name": a.get("name"),
            }
            for a in app_ids
        ],
        "registered_app_ids": len(app_ids),
        "weekly_app_id_limit": WEEKLY_APP_ID_LIMIT,
        "devices": [
            {
                "id": d.get("deviceId"),
                "name": d.get("name"),
                "udid": d.get("deviceNumber"),
                "platform": d.get("devicePlatform"),
            }
            for d in devices
        ],
    }


def revoke_certificate(serial: str, email: str | None = None) -> dict[str, Any]:
    """Revoke one certificate, and say what that just cost.

    Deliberately not refused when the certificate is iPASide's own - it is the user's
    account and there are good reasons to clear it, not least making room when Apple says
    the maximum is reached. But the return value says whether the apps signed on this
    machine have just been invalidated, so a caller can tell the user rather than leaving
    them to discover it when an app stops opening.
    """
    before = overview(email)
    match = next(
        (c for c in before["certificates"] if c["serial"] == serial),
        None,
    )
    if match is None:
        raise developer.DeveloperServicesError(
            f"No certificate with serial {serial} on team {before['team']['id']}."
        )

    with gsa.acting_as(email):
        developer.revoke_certificate(before["team"]["id"], serial)

    return {
        "revoked": serial,
        "machine": match["machine"],
        "was_ours": match["ours"],
        # The one that matters: apps signed here stop launching until iPASide provisions
        # again, and LiveContainer has to be handed the new certificate.
        "invalidates_local_apps": match["in_use_here"],
    }


def delete_app_id(app_id_id: str, email: str | None = None) -> dict[str, Any]:
    """Remove a registered app identifier.

    Frees the identifier for re-use. It does *not* give back one of the week's
    registrations - see :data:`WEEKLY_APP_ID_LIMIT` - so a caller should not describe it
    as making room to install something new this week.
    """
    before = overview(email)
    match = next((a for a in before["app_ids"] if a["id"] == app_id_id), None)

    with gsa.acting_as(email):
        developer.delete_app_id(before["team"]["id"], app_id_id)

    return {
        "deleted": app_id_id,
        "identifier": match["identifier"] if match else None,
        "name": match["name"] if match else None,
        "remaining": before["registered_app_ids"] - 1,
    }

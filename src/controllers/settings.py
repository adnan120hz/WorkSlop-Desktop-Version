from PySide6.QtCore import QSettings

# Settings are stored under the "WorkSlop" organization. Keys that are not
# present there fall back to the legacy "GoldenNugget" and "Nugget"
# organizations so existing users keep their settings after the rename.
# Everything written goes to "WorkSlop", which always takes priority when
# read back.

NEW_ORG = "WorkSlop"
LEGACY_ORGS = ("GoldenNugget", "Nugget")


class Settings:
    """Stores under "WorkSlop" and reads through to "GoldenNugget", "Nugget"."""

    def __init__(self, app: str = "settings"):
        self._primary = QSettings(NEW_ORG, app)
        self._legacies = [QSettings(org, app) for org in LEGACY_ORGS]

    def _read_store(self, key: str) -> QSettings:
        if self._primary.contains(key):
            return self._primary
        for legacy in self._legacies:
            if legacy.contains(key):
                return legacy
        return self._primary

    def contains(self, key: str) -> bool:
        return self._primary.contains(key) or any(
            legacy.contains(key) for legacy in self._legacies
        )

    def value(self, key: str, defaultValue=None, type=None):
        # PySide6 6.11's QSettings.value crashes (SIGBUS in shiboken's
        # checkType) when None is passed positionally for the `type`
        # argument, so only forward it when an actual type is given.
        store = self._read_store(key)
        if type is None:
            return store.value(key, defaultValue)
        return store.value(key, defaultValue, type)

    def setValue(self, key: str, value):
        self._primary.setValue(key, value)

    def remove(self, key: str):
        self._primary.remove(key)
        for legacy in self._legacies:
            legacy.remove(key)

    def allKeys(self) -> list:
        keys = set(self._primary.allKeys())
        for legacy in self._legacies:
            keys.update(legacy.allKeys())
        return list(keys)

    def sync(self):
        self._primary.sync()
        for legacy in self._legacies:
            legacy.sync()

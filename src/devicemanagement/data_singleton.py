from src.devicemanagement.constants import Device

class DataSingleton:
    def __init__(self):
        self.current_device: Device = None
        self.device_available: bool = False
        # Path to the user-provided com.apple.MobileGestalt.plist for this
        # session (Nugget's "Getting the File" flow). SAVED_GESTALT_STRING
        # means "use the per-UDID copy kept in preferences".
        self.gestalt_path: str = None
        self.SAVED_GESTALT_STRING = "saved"
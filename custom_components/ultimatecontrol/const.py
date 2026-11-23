"""Constants for the UltimateControl integration."""

DOMAIN = "ultimatecontrol"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"
CONF_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 80
DEFAULT_NAME = "Ultimate II+"
DEFAULT_SCAN_INTERVAL = 30  # seconds between /v1/info polls
DEFAULT_TIMEOUT = 10  # seconds for ordinary REST calls

# Runners (sidplay, run_prg, run_crt) hold the HTTP response until the device
# has reset and DMA-loaded the file, which takes several seconds.
RUNNER_TIMEOUT = 30

# Path on the Ultimate used when the integration has to upload a file from
# Home Assistant (HVSC stored on the HA host) to the device.
UPLOAD_DIR = "/Temp/UltimateControl"

# Sub-directory of the Home Assistant config dir used as local cache for SID
# files (needed for song-length lookups and for uploads to the device).
SID_CACHE_DIR = "ultimatecontrol"

# File extensions the media browser exposes.
SID_EXTENSIONS = {".sid"}
DISK_EXTENSIONS = {".d64", ".d71", ".d81", ".g64", ".g71"}
PROGRAM_EXTENSIONS = {".prg", ".crt"}

SID_MIME_TYPE = "audio/x-sid"

# Extensions the device can start on its own (SID player, program runner, disk
# drive). Everything else is hidden in the media browser.
RUNNABLE_EXTENSIONS = (
    SID_EXTENSIONS | DISK_EXTENSIONS | PROGRAM_EXTENSIONS | {".d64", ".d71", ".d81"}
)

# Separator between a device path and the sub tune number in a media id.
SONG_SEPARATOR = "#"

MANUFACTURER = "Gideon Zweijtzer / Ultimate"

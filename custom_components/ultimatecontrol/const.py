"""Constants for the UltimateControl integration."""

DOMAIN = "ultimatecontrol"

# Config entry keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"
CONF_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"
# Folder on the Home Assistant host whose SIDs become the favourites folder.
CONF_FAVORITES_FOLDER = "favorites_folder"

DEFAULT_PORT = 80
DEFAULT_NAME = "Ultimate II+"
DEFAULT_FAVORITES_FOLDER = ""
DEFAULT_SCAN_INTERVAL = 30  # seconds between /v1/info polls
DEFAULT_TIMEOUT = 10  # seconds for ordinary REST calls

# Runners (sidplay, run_prg, run_crt) hold the HTTP response until the device
# has reset and DMA-loaded the file, which takes several seconds.
RUNNER_TIMEOUT = 30

# Sub-directory of the Home Assistant config dir: the local SID library
# (``sids``), the favourites (``favorites``) and the song length database.
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

HOST = "0.0.0.0"
PORT = 8080

DEFAULT_FILE = "./assets/logo.png"
BASE_DIR = "videos/"

VIDEO_PATTERNS = ["*.avi", "*.m4v", "*.mkv", "*.mov", "*.mp4"]
VIDEO_COMMAND = "omxplayer --hw --loop --no-osd"
VIDEO_SHORTCUTS = {"play-pause": b" ", "kill": b"q"}

IMAGE_PATTERNS = ["*.gif", "*.jpeg", "*.jpg", "*.png", "*.tif", "*.tiff"]
IMAGE_COMMAND = "fim --quiet --autozoom -T 1"
IMAGE_SHORTCUTS = {"kill": b"q"}

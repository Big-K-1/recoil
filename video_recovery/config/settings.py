# =============================================
# Configuration
# =============================================

# Directory paths — multi-format support (Win/WSL/relative)
SOURCE_DIR = "./source"                 # .exo / .ts source directory
WORKSPACE = "./Workspace_Temp"          # scratch space for intermediate files
OUTPUT_DIR = "./Final_Episodes"         # merged video output

# Processing
TOLERANCE = 1.0                         # PTS stitching tolerance (seconds)
THREADS = 8                             # parallel ffprobe workers
KEEP_SOURCE_FILES = True                # retain original files after copy

# Output
FINAL_OUTPUT_FORMAT = "mp4"             # container for merged video
OUTPUT_RESOLUTION = ""                  # leave empty to keep original resolution

# Timeline-collision algorithm
MAJOR_THRESHOLD = 120                   # minimum duration to treat as a main chain (seconds)
COLLISION_OVERLAP = 15                  # overlap threshold for dedup (seconds)

# Duration classification
DURATION_THRESHOLD = 60                 # above → main content, below → fragment (seconds)
FRAGMENT_DIR_NAME = "fragments"         # subdirectory for short clips

# Dependency checks
CHECK_FFMPEG = True                     # verify ffprobe/ffmpeg are on PATH

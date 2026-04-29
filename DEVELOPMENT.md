# 🎬 Recoil — ExoPlayer Video Recovery Tool — Developer Documentation

## 📖 Overview

Recoil automatically recovers and reassembles fragmented video files (.exo / .ts) from ExoPlayer caches, with support for non-contiguous episode auto-separation.

**Core technology**: Parallel-Universe Collision Algorithm (timeline-overlap detection)

## 🏗️ Project Structure

```
.
├── main.py                          # Main entry point
├── DEVELOPMENT.md                   # This document
├── video_recovery/                  # Core package
│   ├── __init__.py
│   ├── config/                      # Configuration module
│   │   ├── __init__.py
│   │   └── settings.py              # All config parameters
│   ├── core/                        # Core processing module
│   │   ├── __init__.py
│   │   └── processor.py             # Core business logic
│   └── utils/                       # Utility module
│       ├── __init__.py
│       └── helpers.py               # Helper functions
```

## 📚 Core Algorithms

### PTS-Continuity-Based Video Cache Reconstruction

### 0. Cache Mechanics (Key Insight)

> **ExoPlayer stores completed and incomplete fragments mixed together in the same directory** — you cannot judge by file structure; only PTS timestamp analysis is reliable.

**This means**:
- ❌ Filenames / directory structure are unreliable
- ❌ ID grouping is unreliable (IDs can jump / reset during caching)
- ✅ PTS timestamp continuity is the ONLY reliable identification mechanism

---

### 1. DNA Stitch Algorithm (`dna_stitch`)

Stitch fragments by PTS continuity while preserving ad / content type consistency:

```python
# Find PTS-continuous, type-consistent candidates
candidates = [s for s in fragments_pool
              if abs(s["start"] - expected_end) <= TOLERANCE
              and s["is_ad"] == current_is_ad]  # ad attaches only to ad, content only to content
```

---

### 2. Parallel-Universe Collision Detection (`timeline_collision`)

Dynamically identify independent videos rather than hardcoding detection conditions:

```python
# Dynamically detect video-start PTS (duration-weighted statistics)
for c in content_chains:
    pts_key = round(c["start_pts"] / TOLERANCE) * TOLERANCE
    start_pts_counter[pts_key] += c["duration"]  # longer chains carry more weight

video_start_pts = max(start_pts_counter, key=start_pts_counter.get)

# Use this to identify independent videos
main_chains = [c for c in content_chains 
               if abs(c["start_pts"] - video_start_pts) <= TOLERANCE]

# Discard duplicate fragments (PTS range fully contained within a main chain)
if other["start_pts"] >= main["start_pts"] and other["end_pts"] <= main["end_pts"]:
    discard  # duplicate fragment
```

---

### 3. Ad Detection (internal use)

```python
# Based on ffprobe technical parameters; used within DNA stitching to keep fragment type consistent
fps in [25, 30] and audio_sample_rate == 44100  # classified as ad fragment
```

**Note**: Ad detection is only used for stitching logic. Final output is uniformly classified by duration; no separate Ads directory is created.

---

### 4. Key Rules Summary

| Rule | Description |
|------|-------------|
| PTS start ≈ episode beginning | Dynamically detect the most frequent (duration-weighted) start_pts |
| ID grouping is unreliable | IDs can jump / reset during caching |
| File structure is unreliable | Completed / incomplete fragments are mixed together |
| Duplicate fragments are discarded | Chains whose PTS range is fully within a main chain range |
| FFmpeg uses absolute paths | concat.txt MUST use absolute paths to avoid working-directory issues |

## 🔧 Configuration

Edit `video_recovery/config/settings.py`:

```python
# Directory configuration — supports multiple path formats
# Supported formats:
#   - Relative: "./1920x1080_h264" or "1920x1080_h264"
#   - Absolute: "D:\\videos\\cs\\1920x1080_h264" or "D:/videos/cs/1920x1080_h264"
#   - With spaces: "D:\\My Videos\\1920x1080_h264"
SOURCE_DIR = "./source"              # Source file directory
WORKSPACE = "./Workspace_Temp"       # Temp working directory
OUTPUT_DIR = "./Final_Episodes"      # Output directory

# Processing parameters
TOLERANCE = 0.2                      # PTS matching tolerance (seconds)
THREADS = 4                          # Parallel worker count
KEEP_SOURCE_FILES = True             # Retain source files

# Parallel-Universe Collision algorithm parameters
MAJOR_THRESHOLD = 120                # Main content threshold (seconds)
COLLISION_OVERLAP = 15               # Overlap threshold (seconds)

# Duration classification
DURATION_THRESHOLD = 60              # Main content / fragment duration threshold (seconds)
FRAGMENT_DIR_NAME = "fragments"      # Subdirectory for short clips

# Output parameters
FINAL_OUTPUT_FORMAT = "mp4"          # Output container format
OUTPUT_RESOLUTION = ""               # Output resolution (leave empty to retain original)
```

## 🚀 Usage

### Basic Usage
```bash
# Run the program
python main.py

# Show help
python main.py --help

# Modify configuration
# Edit video_recovery/config/settings.py
```

### Execution Flow
1. Check FFmpeg dependency
2. Scan source directory for .exo and .ts files (with progress bar)
3. Group by ID and stitch fragments
4. Extract PTS timestamps
5. DNA stitch into continuous chains
6. Parallel-Universe Collision detection to separate episodes
7. Magnetic attraction of edge fragments to matching episodes
8. Merge video segments (single-threaded to avoid conflicts)
9. Classify by duration (>60s → main content, ≤60s → fragments)

## 🛠️ Development Guide

### Adding New Features

#### 1. Add a config parameter
Add the new parameter in `config/settings.py`, then import it in `core/processor.py` via `from ..config import NEW_PARAM`.

#### 2. Add a utility function
Add it in `utils/helpers.py`, use via `from ..utils import new_function`.

#### 3. Modify core algorithms
Edit the corresponding function in `core/processor.py`.

### Module Dependency Graph
```
main.py → video_recovery.config
        → video_recovery.utils
        → video_recovery.core

core.processor → config
               → utils

utils.helpers → no external dependencies
```

### Testing
After changes, verify syntax:
```bash
python -m py_compile main.py
python -m py_compile video_recovery/core/processor.py
```

## 🎯 FAQ

### 1. How to adjust episode separation sensitivity?
Modify the `COLLISION_OVERLAP` parameter:
- Larger value → more likely to classify as different episodes
- Smaller value → more likely to merge into the same episode

### 2. How to adjust OP/ED detection?
Modify the `MAJOR_THRESHOLD` parameter:
- Larger value → more fragments identified as OP/ED
- Smaller value → more fragments identified as main content

### 3. Which video formats are supported?
- Input: .exo (ExoPlayer-specific format) or .ts (MPEG-TS format)
- Output: copies original .ts files; no format conversion

### 4. How to specify output resolution?
Set `OUTPUT_RESOLUTION = "1920x1080"` or leave empty to retain the original resolution.

### 5. Duration Classification
After merging, the program automatically classifies videos by duration:
- **Duration > 60s** → kept in `Final_Episodes/` root
- **Duration ≤ 60s** → moved to `Final_Episodes/fragments/` subdirectory

Adjust the `DURATION_THRESHOLD` parameter to change the threshold.

## 🔍 Debug Output

The program outputs detailed logs at runtime:

```
[1/6] Scanning and processing files (8 workers)...
  [████████████░░░░░░░░] 60% (740/1234) valid:720 invalid:20
  -> 720 valid fragments processed

[2/6] Stitching continuous time chains...
  -> 8 continuous chains formed

[3/6] Executing spacetime-overlap collision detection...
  -> 2 episodes identified
  -> 3 ad chains identified

[5/6] Merging video segments...
  Starting merge: Video_1
  Complete: Video_1
  Starting merge: Video_2
  Complete: Video_2

[6/6] Classifying by duration (threshold: 60s)...

============================================================
Video processing complete!
   5 videos merged
   Main content: 2 → ./Final_Episodes
   Fragments: 3 → ./Final_Episodes/fragments
   Video_1.mp4 (156.3 MB)
   Video_2.mp4 (142.8 MB)
============================================================
```

## 📦 Dependencies

- Python 3.6+
- FFmpeg + FFprobe
- Third-party libraries: none (stdlib only)

## 📞 Support

When you encounter issues:
1. Verify FFmpeg is correctly installed
2. Check error logs to pinpoint the problem
3. Adjust configuration parameters and retry
4. Refer to this development documentation

---

## 🚀 Version History

### v3.1 — 2026-04-16

**Enhancements**:
1. **Ad false-positive fix** — only fps=30 is flagged as ad, improving accuracy
2. **Episode Pre-grouping multi-stream tracking** — supports simultaneous processing of multiple video sources
3. **Intra-group greedy merge** — optimized fragment merging strategy, improving throughput

---

### v2.8.0 — 2026-04-14

**Bug fixes**:
- **Issue**: ID=3 had two source files; a disguised file passed filtering, causing Ad_Block_14.mp4 merge failure

**Root cause analysis**:
1. **Filtering too permissive**: original code checked `not has_video AND not has_audio`; disguised files with an audio stream passed through
2. **No ID conflict handling**: multi-threaded writes raced — first to write claimed the slot regardless of quality
3. **SOURCE_DIR misconfigured**: pointed to workspace instead of the original cache directory

**Disguised file characteristics** (ffprobe analysis):
```
0/3.51634.1775454299880.v3.exo:
- streams[0]: no codec_type, avg_frame_rate="0/0" ← not a video stream
- streams[1]: codec_type="audio", sample_rate=44100 ← audio only
- No video stream! Actually cache-append data, not a complete segment
```

**Fixes**:
1. **Strict filtering**: must have a valid video stream to pass
   ```python
   if not video_streams:
       return None  # video fragments must have a video stream
   if fps is None or fps <= 0:
       return None  # fps=0 treated as corrupted
   ```
2. **ID conflict resolution**: select best candidate by timestamp, handling ad/main groups separately
3. **Path config**: SOURCE_DIR points to the original cache directory; WORKSPACE holds processed files
4. **Ad filenames**: AD_Seg_X.ts prefix distinguishes ad fragments

---

**Current version**: v3.1  
**Last updated**: 2026-04-16

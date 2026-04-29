# 🎬 Recoil — ExoPlayer TS Fragment Recovery Tool

![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)
![FFmpeg](https://img.shields.io/badge/FFmpeg-required-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

Recoil is a recovery tool for ExoPlayer-cached TS segments, specifically designed for **disguised .exo / .ts files exported by ExoPlayer**. It automatically reassembles fragmented MPEG-TS video segments, supports non-contiguous episode auto-separation, and intelligent ad detection. **No m3u8 file required** — works perfectly even when m3u8 is obfuscated or missing.

## ✨ Core Features

- 🔍 **Smart Ad Detection** — Accurately identifies ad segments based on 30fps frame-rate characteristics (v3.1 fixes false positives)
- 🎯 **Multi-Stream Tracking** — Episode Pre-grouping technology for processing multiple video sources simultaneously
- 🧬 **DNA Splicing Algorithm** — Intelligently joins video segments by PTS timestamp continuity
- 🌌 **Parallel Universe Collision Detection** — Dynamically identifies independent video streams, auto-separating different episodes
- ⚡ **Multi-threaded Processing** — Parallel processing acceleration for higher throughput
- 📊 **Auto Classification** — Classifies by duration (>60s = main content, ≤60s = segment/clip)

## 🚀 Quick Start

### Install Dependencies

```bash
# Install FFmpeg (required)
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to system PATH
```

### Configure the Project

1. Clone the project locally
2. Edit the configuration file `video_recovery/config/settings.py`:

```python
# Set source directory (contains disguised .exo or .ts files)
SOURCE_DIR = "./1920x1080_h264"
WORKSPACE = "./Workspace_Temp"
OUTPUT_DIR = "./Final_Episodes"
```

### Run

```bash
python main.py
```

## 📁 Project Structure

```
.
├── main.py                          # Main entry point
├── README.md                        # Project documentation
├── DEVELOPMENT.md                   # Development docs
├── video_recovery/                   # Core package
│   ├── config/settings.py           # Configuration file
│   ├── core/processor.py            # Core processing logic
│   └── utils/helpers.py             # Utility functions
```

## ⚙️ Configuration Reference

| Parameter | Description | Default |
|------|------|--------|
| SOURCE_DIR | Source file directory (.exo or .ts) | "./1920x1080_h264" |
| WORKSPACE | Temporary working directory | "./Workspace_Temp" |
| OUTPUT_DIR | Output directory | "./Final_Episodes" |
| THREADS | Number of threads | 4 |
| DURATION_THRESHOLD | Main content / segment duration threshold | 60 seconds |
| TOLERANCE | Time matching tolerance | 0.2 seconds |

## 🎯 Technical Highlights

### Ad Detection

- Identifies ad segments based on 30fps frame-rate characteristics
- Supports 44100Hz audio sample rate detection
- Intelligently filters out invalid video files

### Video Reassembly Algorithm

- **DNA Splicing** — Intelligent joining by PTS timestamp continuity
- **Parallel Universe Collision** — Dynamic identification of independent video streams
- **Intra-Group Greedy Merge** — Optimized segment merging strategy

## 📝 Changelog

### v3.1 (2026-04-16)

- ✅ Fixed ad false positives (only 30fps flagged as ads)
- ✅ Episode Pre-grouping multi-stream tracking
- ✅ Optimized intra-group greedy merge algorithm

### v2.8 (2026-04-14)

- ✅ Strict video stream filtering
- ✅ Improved ID conflict handling
- ✅ Fixed path configuration

## 🐛 FAQ

### 1. How are ID conflicts handled?
The system automatically selects the best candidate by timestamp and processes ads and main content separately.

### 2. Which video formats are supported?

- **Input**: ExoPlayer cache-exported .exo or .ts files (both are standard MPEG-TS format segments)
- **Output**: .mp4 format

### 3. How are ad files identified?
Ad files are prefixed with `AD_Seg_X.ts` for easy identification.

---

## 📄 License

MIT License — see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Issues and Pull Requests are welcome!

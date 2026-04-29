"""
Utility module — helper functions
"""
import os
import subprocess
from typing import Tuple, Optional


def normalize_path(path: str) -> str:
    """Normalize path format, supporting multiple path styles with auto-correction.

    Supported formats:
      - Windows absolute: "D:\\videos\\cs\\1920x1080_h264"
      - Relative: "./1920x1080_h264"
      - WSL: "/mnt/d/videos/cs" (converted to Windows format)
      - Paths with spaces: "D:\\My Videos\\1920x1080_h264"
      - Mixed forward/backslash paths

    Returns: normalized absolute path (if it exists) or the original path.
    """
    import platform

    # WSL environment: convert /mnt/x/ → X:\ format
    if path.startswith('/mnt/') and len(path) > 5:
        drive_letter = path[5].upper()
        rest_path = path[6:]  # strip /mnt/x
        path = f"{drive_letter}:{rest_path}"

    # Normalize separators to backslash (Windows format)
    path = path.replace('/', '\\')

    # Trim trailing backslash
    path = path.rstrip('\\')

    # If path is absolute but doesn't exist, return as-is (don't prepend ./)
    if os.path.isabs(path):
        # Under WSL, try converting Windows path to WSL path for existence check
        if platform.system() == 'Linux' and path[0].isalpha() and path[1] == ':':
            wsl_path = f"/mnt/{path[0].lower()}/{path[3:]}"
            if os.path.exists(wsl_path):
                return path  # return Windows format, existence confirmed
        return path

    # If path doesn't exist and is relative, try resolving from CWD
    if not os.path.exists(path):
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path

    # If path already exists, return absolute
    if os.path.exists(path):
        return os.path.abspath(path)

    # Path doesn't exist — return processed relative path
    if not path.startswith('./') and not path.startswith('.\\'):
        path = '.\\' + path

    return path


def run_cmd(cmd: str, capture_output: bool = False):
    """Run a shell command"""
    if capture_output:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    else:
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_video_info(filepath: str) -> Tuple[Optional[float], Optional[float]]:
    """Get video info (start time and duration)"""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=start_time,duration",
           "-of", "csv=p=0", filepath]
    try:
        res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8').strip()
        if res and ',' in res:
            st, dur = res.split(',')
            return float(st), float(dur)
    except Exception:
        pass
    return None, None


def get_video_technical_info(filepath: str) -> Tuple[Optional[float], Optional[int], Optional[int]]:
    """Get video technical info (fps, audio sample rate, video width)

    Returns: (fps, audio_sample_rate, width)
    """
    if not os.path.exists(filepath):
        print(f"  ⚠️  File does not exist: {filepath}")
        return None, None, None

    cmd = [
        "ffprobe", "-hide_banner", "-v", "error",
        "-show_entries", "stream=avg_frame_rate,sample_rate,codec_type,width",
        "-of", "csv=p=0", filepath
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            print(f"  ⚠️  ffprobe command failed {os.path.basename(filepath)}: {result.stderr[:200]}")
            return None, None, None

        res = result.stdout.strip()
        if not res:
            print(f"  ⚠️  No technical info obtained for {os.path.basename(filepath)}")
            return None, None, None

        # Parse multi-line output — ffprobe format:
        # video,<width>,<avg_frame_rate>
        # audio,<sample_rate>,<...>
        lines = res.split('\n')
        fps = None
        audio_sample_rate = None
        width = None

        for line in lines:
            line = line.strip()
            if ',' in line:
                parts = line.split(',')
                if len(parts) >= 3:
                    codec_type = parts[0]

                    if codec_type == 'video':
                        # Video line format: video,width,avg_frame_rate
                        # parts[1] = width, parts[2] = frame rate

                        # Parse width
                        try:
                            width = int(parts[1])
                        except:
                            width = None

                        # Parse frame rate (fractional format, e.g. "25/1")
                        if len(parts) > 2:
                            frame_rate_str = parts[2]
                            if '/' in frame_rate_str:
                                try:
                                    num, den = frame_rate_str.split('/')
                                    fps = float(num) / float(den) if float(den) != 0 else None
                                except:
                                    fps = None
                            else:
                                try:
                                    fps = float(frame_rate_str)
                                except:
                                    fps = None

                    elif codec_type == 'audio':
                        # Audio line format: audio,sample_rate,<...>
                        try:
                            audio_sample_rate = int(parts[1])
                        except:
                            audio_sample_rate = None

        return fps, audio_sample_rate, width
    except Exception as e:
        print(f"  ⚠️  Failed to get technical info for {os.path.basename(filepath)}: {e}")
        return None, None, None


def is_valid_video_file(filepath: str) -> bool:
    """Validate whether a file is a genuine video stream.

    Uses ffprobe to detect if the file contains recognizable video/audio streams.
    Used to filter out files disguised with video extensions.

    Returns: True if valid video file, False otherwise.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, encoding='utf-8', errors='replace')
        if result.returncode == 0 and result.stdout.strip():
            # Output present (video or audio stream) → valid file
            return True
        return False
    except Exception:
        return False


def is_ad_content(filepath: str) -> bool:
    """Detect whether content is an advertisement.

    Ad detection criteria:
    - fps in [25, 30]
    - audio_sample_rate == 44100

    Returns: True if ad, False otherwise.
    """
    if not os.path.exists(filepath):
        print(f"  ⚠️  Ad detection failed: file does not exist {os.path.basename(filepath)}")
        return False

    fps, audio_sample_rate, width = get_video_technical_info(filepath)

    # Print detailed debug info
    print(f"  Technical analysis: {os.path.basename(filepath):<30} fps={fps if fps is not None else 'N/A':<10} "
          f"sample_rate={audio_sample_rate if audio_sample_rate is not None else 'N/A':<10} width={width if width is not None else 'N/A'}")

    # Check if required info is available
    if fps is None and audio_sample_rate is None:
        print(f"  ⚠️  Cannot obtain technical info, skipping ad detection: {os.path.basename(filepath)}")
        return False

    # Detection logic
    fps_match = fps is not None and (fps == 25 or fps == 30)
    audio_match = audio_sample_rate == 44100

    is_ad = fps_match and audio_match

    # Detailed detection result output
    if is_ad:
        print(f"  [AD] Detected as ad: {os.path.basename(filepath)} (fps={fps:.2f} equals 25 or 30, sample_rate={audio_sample_rate}==44100)")
    else:
        reason = []
        if fps is None:
            reason.append("fps unavailable")
        elif not fps_match:
            reason.append(f"fps={fps:.2f} != 25 or 30")

        if audio_sample_rate is None:
            reason.append("sample_rate unavailable")
        elif not audio_match:
            reason.append(f"sample_rate={audio_sample_rate} != 44100")

        reason_str = ", ".join(reason) if reason else "does not meet ad criteria"
        print(f"  [NON-AD] Detected as content: {os.path.basename(filepath)} ({reason_str})")

    return is_ad


def check_dependencies() -> bool:
    """Check required dependencies (FFprobe for ad detection)"""
    from ..config import CHECK_FFMPEG

    if not CHECK_FFMPEG:
        return True

    print("  [Deps] Checking FFprobe (for ad detection)...")

    # Check ffprobe (still needed for extracting video technical info for ad detection)
    try:
        result = subprocess.run(['ffprobe', '-version'], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            print("  FFprobe detected successfully (for ad detection)")
            return True
        else:
            print("  FFprobe detection failed")
            return False
    except FileNotFoundError:
        print("  FFprobe not found (required for ad detection)")
        return False

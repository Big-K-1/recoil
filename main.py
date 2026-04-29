#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ExoPlayer Video Recovery Tool v3.1
Parallel-Universe Collision Algorithm - Single-Pass Optimized Edition
"""

import os
import shutil
import subprocess
from typing import List

from video_recovery.config import (
    SOURCE_DIR, WORKSPACE, OUTPUT_DIR, THREADS,
    KEEP_SOURCE_FILES, DURATION_THRESHOLD, FRAGMENT_DIR_NAME
)
from video_recovery.utils import (
    normalize_path,
    check_dependencies
)
from video_recovery.core import (
    scan_and_process_files,
    dna_stitch,
    timeline_collision,
    merge_episode
)


def setup_directories():
    """Create required directories"""
    if not os.path.exists(WORKSPACE):
        os.makedirs(WORKSPACE)
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)


def get_video_duration(filepath: str) -> float:
    """Get video duration (seconds)"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0


def classify_by_duration(output_dir: str) -> tuple:
    """Classify video files by duration

    duration > DURATION_THRESHOLD: keep in root directory
    duration <= DURATION_THRESHOLD: move to fragments subdirectory

    Returns: (main_count, fragment_count)
    """
    fragment_dir = os.path.join(output_dir, FRAGMENT_DIR_NAME)
    os.makedirs(fragment_dir, exist_ok=True)

    main_count = 0
    fragment_count = 0

    # Iterate video files in the output directory (excluding subdirectories)
    for f in os.listdir(output_dir):
        filepath = os.path.join(output_dir, f)
        # Skip subdirectories
        if os.path.isdir(filepath):
            continue
        # Only process video files
        if not f.lower().endswith(('.mp4', '.ts', '.mkv', '.avi')):
            continue

        duration = get_video_duration(filepath)

        if duration <= DURATION_THRESHOLD:
            # Fragment: move to subdirectory
            target = os.path.join(fragment_dir, f)
            shutil.move(filepath, target)
            fragment_count += 1
        else:
            # Main content: keep in place
            main_count += 1

    return main_count, fragment_count


def print_usage():
    """Print usage instructions"""
    print("""
ExoPlayer Video Recovery Tool v3.1 - Parallel-Universe Collision Algorithm

Features:
  - Smart ad detection (30fps signature detection)
  - Episode Pre-grouping with multi-stream tracking
  - Parallel-universe collision detection, auto-separation of different episodes
  - Reorder by PTS timestamps
  - Multi-threaded parallel processing for speed
  - Auto-classify by duration (>60s = main content, <=60s = fragment)

Usage:
  1. Edit video_recovery/config/settings.py to configure the source directory
  2. Run: python main.py

Config file: video_recovery/config/settings.py
    """)


def main():
    """Main function"""
    print("[>>>] Starting parallel-universe collision separation system...")

    # Display path information
    print(f"  Source: {SOURCE_DIR}")
    print(f"  Workspace: {WORKSPACE}")
    print(f"  Output: {OUTPUT_DIR}")

    # Check dependencies
    if not check_dependencies():
        print("Dependency check failed")
        return

    # Create directories
    setup_directories()

    # ==========================================
    # 1. Scan and process all files (single pass)
    # ==========================================
    print(f"\n[1/6] Scanning and processing files (using {THREADS} threads)...")

    fragments_pool = scan_and_process_files()

    if not fragments_pool:
        print("  No valid video fragments")
        return

    print(f"  -> Processed {len(fragments_pool)} valid fragments")

    # Phase 1 complete, wait for confirmation
    input("\nPress Enter to continue to next step...")

    # ==========================================
    # 2. DNA stitching
    # ==========================================
    print("\n[2/6] Stitching continuous timeline chains...")
    chains = dna_stitch(fragments_pool)
    print(f"  -> Formed {len(chains)} continuous chains")

    # Phase 2 complete, wait for confirmation
    input("\nPress Enter to continue to next step...")

    # ==========================================
    # 3. Parallel-universe collision detection
    # ==========================================
    print("\n[3/6] Running spatiotemporal overlap collision detection...")
    episodes, ad_episodes = timeline_collision(chains)
    print(f"  -> Identified {len(episodes)} episodes")
    if ad_episodes:
        print(f"  -> Identified {len(ad_episodes)} ad chains")

    # Phase 3 complete, wait for confirmation
    input("\nPress Enter to continue to next step...")

    # ==========================================
    # 4. Fragment magnetic-attraction merge complete
    # ==========================================
    print("\n[4/6] Fragment magnetic-attraction merge complete")

    # ==========================================
    # 5. Merge all video segments
    # ==========================================
    print(f"\n[5/6] Merging video segments...")

    merged_files = []

    # Merge all chains (no distinction between ad/main), unified naming
    all_chains = episodes + ad_episodes
    for idx, ep_chains in enumerate(all_chains):
        if ep_chains:
            ep_name = f"Video_{idx + 1}"
            print(f"  Merging: {ep_name}")
            result = merge_episode(ep_chains, OUTPUT_DIR, ep_name)
            if result:
                print(f"  Done: {ep_name}")
                merged_files.append(result)

    # ==========================================
    # 6. Classify videos by duration
    # ==========================================
    print(f"\n[6/6] Classifying by duration (threshold: {DURATION_THRESHOLD}s)...")
    main_count, fragment_count = classify_by_duration(OUTPUT_DIR)

    # Summary
    print("\n" + "=" * 60)
    if merged_files:
        print("Video processing complete!")
        print(f"   Total merged: {len(merged_files)} videos")
        print(f"   Main content: {main_count} -> {OUTPUT_DIR}")
        if fragment_count > 0:
            print(f"   Fragments: {fragment_count} -> {os.path.join(OUTPUT_DIR, FRAGMENT_DIR_NAME)}")

        # Display file sizes in main content directory
        for f in os.listdir(OUTPUT_DIR):
            filepath = os.path.join(OUTPUT_DIR, f)
            if os.path.isfile(filepath) and f.lower().endswith(('.mp4', '.ts')):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                print(f"   {f} ({size_mb:.1f} MB)")
    else:
        print("No videos were merged")
    print("=" * 60)

    # ==========================================
    # 7. Ask whether to delete temporary workspace files
    # ==========================================
    if os.path.exists(WORKSPACE):
        print(f"\nTemporary workspace: {WORKSPACE}")
        try:
            # Calculate temporary directory size
            total_size = 0
            for root, dirs, files in os.walk(WORKSPACE):
                for f in files:
                    total_size += os.path.getsize(os.path.join(root, f))
            size_mb = total_size / (1024 * 1024)
            print(f"Disk usage: {size_mb:.1f} MB")
        except:
            pass

        choice = input("\nDelete temporary workspace files? [y/N]: ").strip().lower()
        if choice == 'y':
            try:
                shutil.rmtree(WORKSPACE)
                print(f"Deleted: {WORKSPACE}")
            except Exception as e:
                print(f"Deletion failed: {e}")
        else:
            print("Temporary workspace files kept")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print_usage()
    else:
        main()

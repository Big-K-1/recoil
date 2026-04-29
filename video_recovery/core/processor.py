"""
Core processing module — video recovery pipeline
"""
import os
import json
import shutil
import subprocess
import concurrent.futures
from typing import List, Dict, Tuple, Optional

from ..config import (
    OUTPUT_DIR, WORKSPACE, TOLERANCE, THREADS,
    KEEP_SOURCE_FILES, FINAL_OUTPUT_FORMAT, OUTPUT_RESOLUTION,
    MAJOR_THRESHOLD, COLLISION_OVERLAP, SOURCE_DIR
)
from ..utils.helpers import run_cmd, get_video_info, normalize_path
from ..utils.logger import logger


def process_single_file(filepath: str) -> Optional[Dict]:
    """Process a single file: validate + extract metadata

    Strict filtering criteria:
    - Must contain a video stream (audio-only fragments are rejected)
    - ffprobe must parse successfully
    - Must be able to extract a valid segment ID

    Returns None for invalid files, with detailed filter-reason logging.
    """
    filename = os.path.basename(filepath)

    # ffprobe full metadata extraction
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=start_time,duration:stream=codec_type,avg_frame_rate,sample_rate,width",
        "-of", "json", filepath
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            logger.debug(f"[FILTER] ffprobe failed: {filename}")
            return None

        data = json.loads(result.stdout)
        streams = data.get('streams', [])

        # === Strict filtering: must have a video stream ===
        video_streams = [s for s in streams if s.get('codec_type') == 'video']
        audio_streams = [s for s in streams if s.get('codec_type') == 'audio']

        if not video_streams:
            logger.debug(f"[FILTER] No video stream: {filename} (only {len(audio_streams)} audio streams)")
            return None

        # Validate video stream (must have width and frame rate info)
        video_stream = video_streams[0]
        width = video_stream.get('width')
        rate_str = video_stream.get('avg_frame_rate', '0/1')

        # Parse frame rate
        fps = None
        if '/' in rate_str:
            num, den = rate_str.split('/')
            if float(den) != 0:
                fps = float(num) / float(den)

        # Zero or invalid fps → treat as corrupted
        if fps is None or fps <= 0:
            logger.debug(f"[FILTER] Corrupted video stream: {filename} (fps={rate_str})")
            return None

        # Extract audio sample rate
        audio_rate = None
        if audio_streams:
            audio_rate = int(audio_streams[0].get('sample_rate', 0))

        # Ad detection: ONLY fps=30 AND audio=44100 is treated as ad
        # NOTE: fps=25+44100 content may be legitimate (e.g. certain anime) — do NOT flag as ad
        is_ad = abs(fps - 30) < 0.1 and audio_rate == 44100

        # Extract segment ID
        try:
            if filename.startswith('Seg_'):
                vid_id = int(filename.split('_')[1].split('.')[0])
            else:
                # Format: [id].[offset].[timestamp].v3.exo or [id].xxx.ts
                vid_id = int(filename.split('.')[0])
        except (ValueError, IndexError):
            logger.debug(f"[FILTER] ID extraction failed: {filename}")
            return None

        # Extract timing info
        fmt = data.get('format', {})
        start_time = float(fmt.get('start_time', 0))
        duration = float(fmt.get('duration', 0))

        if duration <= 0:
            logger.debug(f"[FILTER] Invalid duration: {filename} (duration={duration})")
            return None

        # Extract timestamp (used for tie-breaking during ID conflict resolution)
        timestamp = None
        parts = filename.split('.')
        if len(parts) >= 3 and parts[-1] in ['exo', 'ts', 'v3.exo']:
            try:
                # Format: [id].[offset].[timestamp].v3.exo
                # timestamp is the second-to-last numeric component (strip .v3.exo)
                timestamp = int(parts[-3]) if len(parts) >= 4 else int(parts[2])
            except ValueError:
                pass

        logger.debug(f"[VALID] {filename}: ID={vid_id}, PTS={start_time:.1f}s-{start_time+duration:.1f}s, "
                     f"fps={fps}, audio={audio_rate}, ad={is_ad}, ts={timestamp}")

        return {
            "path": filepath,
            "id": vid_id,
            "start": start_time,
            "duration": duration,
            "end": start_time + duration,
            "is_ad": is_ad,
            "fps": fps,
            "audio_rate": audio_rate,
            "width": width,
            "timestamp": timestamp,
            "source_file": filepath
        }

    except subprocess.TimeoutExpired:
        logger.debug(f"[FILTER] ffprobe timeout: {filename}")
        return None
    except json.JSONDecodeError:
        logger.debug(f"[FILTER] JSON parse failed: {filename}")
        return None
    except Exception as e:
        logger.debug(f"[FILTER] Processing exception: {filename} - {e}")
        return None


def scan_and_process_files() -> List[Dict]:
    """Recursively scan and process all source files (single-pass + ID conflict resolution)

    Pipeline:
    1. Scan all .exo and .ts files recursively
    2. Multi-threaded validation — reject invalid files (must have video stream)
    3. ID conflict resolution: for duplicate IDs, select the best candidate (by timestamp or file size)
    4. Copy valid files to workspace

    Returns the fragments_pool list, each entry containing full metadata.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import sys

    normalized_source_dir = normalize_path(SOURCE_DIR)

    if not os.path.exists(normalized_source_dir):
        print(f"  X Source directory does not exist: {normalized_source_dir}")
        print(f"    Original path: {SOURCE_DIR}")
        return []

    # Recursive scan for .exo and .ts files
    all_files = []
    print(f"  [Scan] Recursive scan: {normalized_source_dir}")

    for root, dirs, files in os.walk(normalized_source_dir):
        for f in files:
            if f.endswith('.exo') or f.endswith('.ts'):
                all_files.append(os.path.join(root, f))

    if not all_files:
        print(f"  X No .exo or .ts files found")
        return []

    total = len(all_files)
    print(f"  [Scan] Found {total} candidate files")
    print(f"  [Process] Validating with {THREADS} parallel workers...")

    # Ensure workspace directory exists
    os.makedirs(WORKSPACE, exist_ok=True)

    # === Multi-threaded validation ===
    valid_candidates = []  # all candidates that pass validation
    invalid_count = 0
    progress_state = {'completed': 0, 'valid': 0, 'invalid': 0}

    def update_progress():
        percent = progress_state['completed'] * 100 // total
        filled = percent // 5
        bar = '█' * filled + '░' * (20 - filled)
        sys.stdout.write(f'\r  [{bar}] {percent:3d}% ({progress_state["completed"]}/{total}) '
                         f'valid:{progress_state["valid"]} invalid:{progress_state["invalid"]}')
        sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {executor.submit(process_single_file, fp): fp for fp in all_files}

        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_candidates.append(result)
                progress_state['valid'] += 1
            else:
                invalid_count += 1
                progress_state['invalid'] += 1
            progress_state['completed'] += 1
            update_progress()

    print()
    print(f"  [Validate] Done — valid candidates: {len(valid_candidates)}, invalid: {invalid_count}")

    if not valid_candidates:
        return []

    # === ID conflict resolution ===
    # Duplicate IDs can occur (different offsets); select the best candidate
    id_groups = {}
    for cand in valid_candidates:
        vid_id = cand['id']
        if vid_id not in id_groups:
            id_groups[vid_id] = []
        id_groups[vid_id].append(cand)

    # Select the best candidate per ID
    best_candidates = []
    conflict_resolved = 0
    conflict_logged = []

    for vid_id, candidates in id_groups.items():
        if len(candidates) > 1:
            # ID conflict — select best candidate by rules:
            # 1. Prefer smaller timestamp (earlier download, usually the full segment)
            # 2. If no timestamp, prefer larger file
            # 3. For same-type ads, prefer smaller PTS

            # Split by ad / non-ad
            ad_cands = [c for c in candidates if c['is_ad']]
            main_cands = [c for c in candidates if not c['is_ad']]

            # Select best from each group independently
            if ad_cands:
                ad_best = sorted(ad_cands, key=lambda x: (
                    x['timestamp'] if x['timestamp'] else float('inf'),
                    -os.path.getsize(x['source_file'])
                ))[0]
                best_candidates.append(ad_best)
                conflict_logged.append(f"ID={vid_id} AD conflict: {len(ad_cands)} candidates → selected {os.path.basename(ad_best['source_file'])}")

            if main_cands:
                main_best = sorted(main_cands, key=lambda x: (
                    x['timestamp'] if x['timestamp'] else float('inf'),
                    -os.path.getsize(x['source_file'])
                ))[0]
                best_candidates.append(main_best)
                conflict_logged.append(f"ID={vid_id} MAIN conflict: {len(main_cands)} candidates → selected {os.path.basename(main_best['source_file'])}")

            conflict_resolved += len(candidates) - 1
        else:
            best_candidates.append(candidates[0])

    # Print conflict resolution summary
    if conflict_logged:
        print(f"  [Conflict] ID conflicts resolved: {conflict_resolved} filtered out")
        for log in conflict_logged[:10]:  # show first 10 only
            print(f"    {log}")
        if len(conflict_logged) > 10:
            print(f"    ... and {len(conflict_logged) - 10} more conflicts")

        for log in conflict_logged:
            logger.debug(f"[ID conflict] {log}")

    # === Copy valid files to workspace ===
    print(f"  [Copy] Copying {len(best_candidates)} valid segments to workspace...")
    fragments_pool = []

    for cand in best_candidates:
        source_path = cand['source_file']
        vid_id = cand['id']

        # Unified naming: all segments use Seg_X.ts (no ad/main distinction)
        dest_name = f"Seg_{vid_id}.ts"
        dest_path = os.path.join(WORKSPACE, dest_name)

        # If destination already exists, check if it's the same source
        if os.path.exists(dest_path):
            # Duplicate name already handled above — skip copy
            cand['path'] = dest_path
            fragments_pool.append(cand)
            logger.debug(f"[Copy] Skipped (already exists): {dest_name}")
            continue

        try:
            shutil.copy2(source_path, dest_path)
            cand['path'] = dest_path
            fragments_pool.append(cand)
        except Exception as e:
            logger.warning(f"[Copy] Copy failed: {source_path} -> {dest_path}, {e}")

    print(f"  [Done] Final valid segments: {len(fragments_pool)}")
    return fragments_pool


def _episode_pregroup(fragments: List[Dict]) -> List[List[Dict]]:
    """Episode Pre-grouping: multi-stream tracking by ID + PTS to separate
    interleaved downloads of different videos.

    Core principle:
    - EXO downloader fetches one episode per session, producing contiguous-ID
      segments with monotonically increasing PTS
    - When multiple downloads interleave, a single ID range contains multiple PTS streams
    - Traverse by ascending ID, maintain multiple active streams, assign each
      new segment to the stream with the closest PTS
    - PTS reset to near-origin → new episode starts, create a new stream
    - Stream idle for > 200 IDs → closed

    Returns a list of groups, each containing segments belonging to the same video.
    """
    if not fragments:
        return []

    sorted_frags = sorted(fragments, key=lambda x: x["id"])

    class _Stream:
        def __init__(self, seg):
            self.segs = [seg]
            self.last_pts = seg["end"]
            self.last_id = seg["id"]
            self.closed = False

        def can_accept(self, seg):
            if self.closed:
                return False
            id_gap = seg["id"] - self.last_id
            if id_gap > 200:
                self.closed = True
                return False
            diff = seg["start"] - self.last_pts
            # PTS continuation: allow -2s (overlap) to +30s (gap after ad removal)
            return -2.0 <= diff <= 30

        def distance(self, seg):
            return abs(seg["start"] - self.last_pts)

        def add(self, seg):
            self.segs.append(seg)
            self.last_pts = seg["end"]
            self.last_id = seg["id"]

    streams = []
    for seg in sorted_frags:
        candidates = [(s, s.distance(seg)) for s in streams if s.can_accept(seg)]
        if candidates:
            best, _ = min(candidates, key=lambda x: x[1])
            best.add(seg)
        else:
            streams.append(_Stream(seg))

    # Split into major streams and fragments (< 20 segments → fragment)
    big = [s for s in streams if len(s.segs) >= 20]
    small = [s for s in streams if len(s.segs) < 20]

    # Merge fragments into the nearest major stream by PTS range coverage + ID proximity
    for ss in small:
        for seg in ss.segs:
            best_stream = None
            best_score = float('inf')
            for bs in big:
                bs_pts_min = min(s["start"] for s in bs.segs)
                bs_pts_max = max(s["end"] for s in bs.segs)
                if bs_pts_min - 10 <= seg["start"] <= bs_pts_max + 10:
                    min_id_dist = min(abs(seg["id"] - s["id"]) for s in bs.segs)
                    if min_id_dist < best_score:
                        best_score = min_id_dist
                        best_stream = bs
            if best_stream:
                best_stream.segs.append(seg)
            else:
                logger.debug(f"[PreGroup] Orphan seg: ID={seg['id']} PTS={seg['start']:.1f}")

    groups = [s.segs for s in big]

    # Logging
    logger.debug(f"[PreGroup] {len(streams)} streams -> {len(big)} groups, {len(small)} small merged")
    for i, g in enumerate(sorted(groups, key=lambda g: min(s["id"] for s in g))):
        ids = [s["id"] for s in g]
        dur = sum(s["duration"] for s in g)
        logger.debug(f"  Group {i+1}: {len(g)} segs, IDs={min(ids)}-{max(ids)}, dur={dur/60:.1f}min")

    return groups


def dna_stitch(fragments_pool: List[Dict]) -> List[List[Dict]]:
    """DNA Stitch algorithm — Episode Pre-grouping first, then PTS stitching per group.

    Pipeline:
    1. Separate ad / non-ad segments
    2. Episode pre-grouping on non-ad segments (multi-stream tracking)
    3. Independent PTS stitching per group (greedy by timestamp)
    4. Independent PTS stitching for ad segments
    """
    # Separate ads from main content
    ad_pool = [s for s in fragments_pool if s.get("is_ad", False)]
    main_pool = [s for s in fragments_pool if not s.get("is_ad", False)]

    logger.debug(f"[DNA Stitch] Input: {len(main_pool)} main, {len(ad_pool)} ad")

    # Episode Pre-grouping (main content only)
    episode_groups = _episode_pregroup(main_pool)
    print(f"  [Pre-group] {len(episode_groups)} video groups detected")

    # PTS stitching within each group
    all_chains = []
    stitch_count = 0

    for gi, group in enumerate(episode_groups):
        pool = list(group)
        group_chains = []

        while pool:
            pool.sort(key=lambda x: x["start"])
            current_seg = pool.pop(0)
            current_chain = [current_seg]

            while True:
                expected_start = current_seg["end"]
                best_match = None
                min_id_diff = float('inf')

                candidates = [s for s in pool
                              if abs(s["start"] - expected_start) <= TOLERANCE]
                if candidates:
                    for cand in candidates:
                        id_diff = abs(cand["id"] - current_seg["id"])
                        if id_diff < min_id_diff:
                            min_id_diff = id_diff
                            best_match = cand

                if best_match:
                    current_chain.append(best_match)
                    pool.remove(best_match)
                    current_seg = best_match
                    stitch_count += 1
                else:
                    break

            group_chains.append(current_chain)

        # Intra-group post-processing: merge broken chains + discard duplicates
        # Chains within the same group logically belong to the same video;
        # they were split only because of ad segments or small PTS gaps.

        if len(group_chains) > 1:
            # 1. Sort by PTS start
            group_chains.sort(key=lambda c: c[0]["start"])

            # 2. Greedy merge: monotonically increasing PTS chains are joined;
            #    PTS rollback chains (re-downloaded duplicates) are discarded
            main_chain = group_chains[0]
            main_end = main_chain[-1]["end"]
            discarded = 0

            for gc in group_chains[1:]:
                gc_start = gc[0]["start"]
                gc_end = gc[-1]["end"]

                if gc_start >= main_end - 5:
                    # PTS continues forward (allow 5s overlap)
                    # No gap limit — chains in the same group belong to the same video
                    main_chain = main_chain + gc
                    main_end = gc_end
                elif gc_end > main_end:
                    # Partial PTS rollback but extends further — take the tail
                    main_chain = main_chain + gc
                    main_end = gc_end
                else:
                    # PTS fully covered by existing chain — duplicate, discard
                    gc_dur = sum(s["duration"] for s in gc)
                    logger.debug(f"[DNA Stitch] Group {gi+1}: discard dup chain "
                                 f"PTS={gc_start:.0f}-{gc_end:.0f} ({gc_dur/60:.1f}min)")
                    discarded += 1

            group_chains = [main_chain]
            if discarded:
                logger.debug(f"[DNA Stitch] Group {gi+1}: {discarded} dup chains discarded")

        # Each group typically yields 1 main chain (gaps may cause splits)
        all_chains.extend(group_chains)
        ids = [s["id"] for seg_list in group_chains for s in seg_list]
        logger.debug(f"  Group {gi+1}: {len(group_chains)} chains from {len(group)} segs")

    # Independent PTS stitching for ads
    ad_chains = []
    ad_pool_copy = list(ad_pool)
    while ad_pool_copy:
        ad_pool_copy.sort(key=lambda x: x["start"])
        current_seg = ad_pool_copy.pop(0)
        current_chain = [current_seg]

        while True:
            expected_start = current_seg["end"]
            best_match = None
            min_id_diff = float('inf')

            candidates = [s for s in ad_pool_copy
                          if abs(s["start"] - expected_start) <= TOLERANCE]
            if candidates:
                for cand in candidates:
                    id_diff = abs(cand["id"] - current_seg["id"])
                    if id_diff < min_id_diff:
                        min_id_diff = id_diff
                        best_match = cand

            if best_match:
                current_chain.append(best_match)
                ad_pool_copy.remove(best_match)
                current_seg = best_match
                stitch_count += 1
            else:
                break

        ad_chains.append(current_chain)

    all_chains.extend(ad_chains)

    # Logging
    logger.debug(f"[DNA Stitch] Total: {len(all_chains)} chains ({len(all_chains)-len(ad_chains)} main, {len(ad_chains)} ad), {stitch_count} stitches")
    for i, chain in enumerate(all_chains):
        duration = sum(s["duration"] for s in chain)
        start_pts = chain[0]["start"]
        end_pts = chain[-1]["end"]
        ids = [s["id"] for s in chain]
        is_ad = any(s.get("is_ad") for s in chain)
        type_label = "AD" if is_ad else "MAIN"
        logger.debug(f"  Chain {i+1}: {len(chain)} segs [{type_label}], PTS={start_pts:.1f}s-{end_pts:.1f}s, "
                     f"dur={duration:.1f}s, IDs={min(ids)}-{max(ids)}")

    return all_chains


def timeline_collision(chains: List[List[Dict]]) -> Tuple[List[List[Dict]], List[List[Dict]]]:
    """Parallel-Universe Collision Detection — separate distinct episodes.

    Since dna_stitch already includes episode pre-grouping, this function handles:
    1. Separate ad chains from content chains
    2. Cluster content chains by ID range (merge broken chains from the same episode group)
    3. Remove duplicate chains (PTS coverage > 80% by a longer chain)
    4. Merge PTS-adjacent and ID-adjacent chains (heal splits)

    Returns: (episodes, ad_episodes)
    """
    ID_OVERLAP_THRESHOLD = 0.1
    PTS_MERGE_GAP = 60
    ID_MERGE_GAP = 100

    # Compute chain stats
    chain_stats = []
    for c in chains:
        start = c[0]["start"]
        end = c[-1]["end"]
        duration = sum(seg["duration"] for seg in c)
        ids = sorted(set(s["id"] for s in c))
        id_set = set(ids)

        has_ad_fragments = any(s.get("is_ad", False) for s in c)

        chain_stats.append({
            "chain": c,
            "min_id": min(ids),
            "max_id": max(ids),
            "id_set": id_set,
            "start_pts": start,
            "end_pts": end,
            "duration": duration,
            "is_ad_chain": has_ad_fragments,
        })

    # Separate ad chains and content chains
    ad_chains = [c for c in chain_stats if c["is_ad_chain"]]
    content_chains = [c for c in chain_stats if not c["is_ad_chain"]]

    logger.debug("[Collision] === Chain PTS range overview ===")
    for i, cs in enumerate(chain_stats):
        chain_type = "AD" if cs["is_ad_chain"] else "MAIN"
        logger.debug(f"  [{chain_type}] Chain {i+1}: PTS={cs['start_pts']:.1f}s-{cs['end_pts']:.1f}s, "
                     f"dur={cs['duration']:.1f}s, IDs={cs['min_id']}-{cs['max_id']}, {len(cs['chain'])}segs")

    print(f"  -> Raw chains: {len(ad_chains)} ad, {len(content_chains)} content")

    # =====================================================
    # Phase 1: Cluster by ID range (Union-Find)
    # =====================================================
    n = len(content_chains)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def id_ranges_overlap(cs_a, cs_b):
        if cs_a["max_id"] < cs_b["min_id"] or cs_b["max_id"] < cs_a["min_id"]:
            return False
        overlap = len(cs_a["id_set"] & cs_b["id_set"])
        smaller = min(len(cs_a["id_set"]), len(cs_b["id_set"]))
        if smaller == 0:
            return False
        return (overlap / smaller) >= ID_OVERLAP_THRESHOLD

    for i in range(n):
        for j in range(i + 1, n):
            if id_ranges_overlap(content_chains[i], content_chains[j]):
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(i)

    # =====================================================
    # Phase 2: Dedup within each group
    # =====================================================
    kept_chains = []
    total_discarded = 0

    for root, members in groups.items():
        if len(members) == 1:
            kept_chains.append(content_chains[members[0]])
            continue

        sorted_members = sorted(members, key=lambda m: content_chains[m]["duration"], reverse=True)
        kept = []
        for idx in sorted_members:
            cs = content_chains[idx]
            is_covered = False
            for k_idx in kept:
                k_cs = content_chains[k_idx]
                pts_overlap_start = max(cs["start_pts"], k_cs["start_pts"])
                pts_overlap_end = min(cs["end_pts"], k_cs["end_pts"])
                if pts_overlap_end > pts_overlap_start:
                    overlap_duration = pts_overlap_end - pts_overlap_start
                    coverage = overlap_duration / cs["duration"] if cs["duration"] > 0 else 0
                    if coverage > 0.8:
                        logger.debug(f"[Collision] DISCARD: IDs={cs['min_id']}-{cs['max_id']} "
                                     f"PTS={cs['start_pts']:.1f}-{cs['end_pts']:.1f} dur={cs['duration']:.0f}s "
                                     f"(covered {coverage:.0%} by IDs={k_cs['min_id']}-{k_cs['max_id']})")
                        is_covered = True
                        total_discarded += 1
                        break
            if not is_covered:
                kept.append(idx)

        for idx in kept:
            kept_chains.append(content_chains[idx])

    print(f"  -> After ID-group dedup: {len(kept_chains)} chains kept, {total_discarded} discarded")

    # =====================================================
    # Phase 3: Merge PTS-adjacent + ID-adjacent chains
    # =====================================================
    kept_chains.sort(key=lambda c: (c["min_id"], c["start_pts"]))

    merged = []
    merged_count = 0
    i = 0
    while i < len(kept_chains):
        current = kept_chains[i]
        while i + 1 < len(kept_chains):
            next_c = kept_chains[i + 1]
            pts_gap = next_c["start_pts"] - current["end_pts"]
            id_gap = next_c["min_id"] - current["max_id"]

            if 0 <= pts_gap <= PTS_MERGE_GAP and 0 <= id_gap <= ID_MERGE_GAP:
                logger.debug(f"[Collision] MERGE: IDs={current['min_id']}-{current['max_id']} "
                             f"+ IDs={next_c['min_id']}-{next_c['max_id']} "
                             f"[pts_gap={pts_gap:.1f}s, id_gap={id_gap}]")
                current["chain"] = current["chain"] + next_c["chain"]
                current["end_pts"] = next_c["end_pts"]
                current["max_id"] = max(current["max_id"], next_c["max_id"])
                current["min_id"] = min(current["min_id"], next_c["min_id"])
                current["id_set"] = current["id_set"] | next_c["id_set"]
                current["duration"] = sum(seg["duration"] for seg in current["chain"])
                merged_count += 1
                i += 1
            else:
                break
        merged.append(current)
        i += 1

    print(f"  -> After PTS-adjacent merge: {len(merged)} chains ({merged_count} merges)")

    merged.sort(key=lambda x: x["start_pts"])

    print(f"\n  Final video count: {len(merged)}")
    for i, mc in enumerate(merged):
        print(f"     Video {i+1}: PTS={mc['start_pts']:.1f}s-{mc['end_pts']:.1f}s "
              f"dur={mc['duration']:.1f}s ({mc['duration']/60:.1f}min) "
              f"IDs={mc['min_id']}-{mc['max_id']}")

    episodes = [[mc] for mc in merged]

    print(f"\n  Ad chains: {len(ad_chains)}")
    ad_episodes = [[ac] for ac in ad_chains]

    for i, ac in enumerate(ad_chains):
        logger.debug(f"[Ad Chain {i+1}] PTS={ac['start_pts']:.1f}s-{ac['end_pts']:.1f}s, "
                     f"dur={ac['duration']:.1f}s, {len(ac['chain'])} segs, IDs={ac['min_id']}-{ac['max_id']}")

    logger.debug("[Collision] === Final output mapping ===")
    for i, ep in enumerate(episodes):
        mc = ep[0]
        logger.debug(f"  Video_{i+1}: PTS={mc['start_pts']:.1f}s-{mc['end_pts']:.1f}s, "
                     f"dur={mc['duration']:.1f}s, {len(mc['chain'])}segs")

    return episodes, ad_episodes


def merge_episode(ep_chains: List[Dict], target_dir: str, ep_name: str) -> Optional[str]:
    """Merge a single episode.

    Args:
        ep_chains: episode chain list
        target_dir: output directory
        ep_name: episode name (unified Video_X naming)
    """
    # Ensure target directory exists
    os.makedirs(target_dir, exist_ok=True)

    concat_file = os.path.join(target_dir, "concat.txt")

    # Write concat file (use absolute paths to avoid FFmpeg path-resolution issues)
    with open(concat_file, 'w', encoding='utf-8') as f:
        for stat in ep_chains:
            for seg in stat["chain"]:
                # Convert to absolute path
                abs_path = os.path.abspath(seg['path'])
                f.write(f"file '{abs_path}'\n")

    output_file = os.path.join(target_dir, f"{ep_name}.{FINAL_OUTPUT_FORMAT}")

    # Build FFmpeg command
    ffmpeg_cmd = f'ffmpeg -v warning -y -f concat -safe 0 -i "{concat_file}"'

    if OUTPUT_RESOLUTION:
        ffmpeg_cmd += f' -vf "scale={OUTPUT_RESOLUTION}:force_original_aspect_ratio=decrease,pad={OUTPUT_RESOLUTION}:(ow-iw)/2:(oh-ih)/2"'
        ffmpeg_cmd += f' -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k'
    else:
        ffmpeg_cmd += f' -c copy'

    ffmpeg_cmd += f' "{output_file}"'

    result = run_cmd(ffmpeg_cmd, capture_output=True)

    if result.returncode == 0:
        # Clean up concat file only (keep ts files)
        if os.path.exists(concat_file):
            os.remove(concat_file)
        return output_file
    else:
        print(f"  X Merge failed: {result.stderr}")
        return None

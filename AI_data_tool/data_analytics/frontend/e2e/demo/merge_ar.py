"""Lay the Arabic narration onto the recorded demo and write the subtitles.

    python merge_ar.py [narration_dir] [output_dir]

Reads <narration_dir>/timeline.json (step start times, written by record_demo_ar.mjs),
<narration_dir>/durations.json (clip files, written by tts_ar.py) and
<narration_dir>/raw_ar.webm, and writes
    <output_dir>/datalytics_demo_ar.mp4   (H.264 1920x1080 + AAC voice-over)
    <output_dir>/datalytics_demo_ar.srt   (Arabic subtitles, same timings)
Needs ffmpeg/ffprobe on PATH.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
NARR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'demo_output', 'narration')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'demo_output')


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def wrap(text, width=58):
    """Two balanced lines at most, broken on a space."""
    if len(text) <= width:
        return text
    mid = len(text) // 2
    cut = min((i for i, c in enumerate(text) if c == ' '), key=lambda i: abs(i - mid), default=None)
    return text if cut is None else text[:cut] + '\n' + text[cut + 1:]


def probe_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def marker_starts(video, n):
    """Step index -> first video second showing that step's corner marker
    (grey 16 + 10*i, see record_demo_ar.mjs), read at 25 fps."""
    fps = 25
    cmd = ['ffmpeg', '-v', 'error', '-i', video, '-vf',
           f'fps={fps},crop=6:6:1913:1073,scale=1:1:flags=area,format=gray', '-f', 'rawvideo', '-']
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    starts, run_idx, run_len = {}, None, 0
    for frame, v in enumerate(data):
        idx = round((v - 16) / 10)
        if 0 <= idx < n and abs(v - (16 + idx * 10)) <= 4:
            run_len = run_len + 1 if idx == run_idx else 1
            run_idx = idx
            if run_len == 3 and idx not in starts:
                starts[idx] = (frame - 2) / fps
        else:
            run_idx, run_len = None, 0
    return starts


def main():
    with open(os.path.join(NARR, 'timeline.json'), encoding='utf-8') as f:
        timeline = json.load(f)
    with open(os.path.join(NARR, 'durations.json'), encoding='utf-8') as f:
        clips = json.load(f)
    video = os.path.join(NARR, 'raw_ar.webm')
    vdur = probe_duration(video)

    # Place clips; never let one start before the previous has finished.
    steps = timeline['steps']
    found = marker_starts(video, len(steps))
    # Where a marker was not seen, fall back to the wall clock plus the typical drift.
    drifts = sorted(found[i] - steps[i]['start'] for i in found)
    drift = drifts[len(drifts) // 2] if drifts else 0.0
    print(f'step markers found: {len(found)}/{len(steps)}; median video-vs-clock drift {drift:+.2f}s')
    for i, s in enumerate(steps):
        s['video_start'] = found.get(i, s['start'] + drift)

    placed, prev_end = [], 0.0
    for step in steps:
        c = clips.get(step['id'])
        if not c:
            continue
        # Clip files were written on the PC; resolve them next to durations.json.
        f = os.path.join(NARR, os.path.basename(c['file'].replace('\\', '/')))
        start = max(step['video_start'] + 0.1, prev_end + 0.1)
        placed.append((start, c['seconds'], f, step['text']))
        prev_end = start + c['seconds']

    with open(os.path.join(OUT, 'datalytics_demo_ar.srt'), 'w', encoding='utf-8') as f:
        for i, (start, secs, _, text) in enumerate(placed, 1):
            f.write(f'{i}\n{srt_time(start)} --> {srt_time(start + secs)}\n{wrap(text)}\n\n')

    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', video]
    for _, _, f, _ in placed:
        cmd += ['-i', f]
    parts = []
    for i, (start, _, _, _) in enumerate(placed, 1):
        ms = int(start * 1000)
        parts.append(f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]')
    mix = ''.join(f'[a{i}]' for i in range(1, len(placed) + 1))
    parts.append(f'{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,'
                 f'volume=1.4,apad,atrim=0:{vdur:.3f}[aout]')
    out_mp4 = os.path.join(OUT, 'datalytics_demo_ar.mp4')
    # Paint over the 8x8 step marker with the patch just left of it.
    parts.insert(0, '[0:v]split[v0][v1];[v1]crop=8:8:1904:1072[patch];[v0][patch]overlay=1912:1072[vout]')
    cmd += ['-filter_complex', ';'.join(parts), '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-t', f'{vdur:.3f}', out_mp4]
    subprocess.run(cmd, check=True)
    print(f'{out_mp4}: {vdur:.1f}s, {len(placed)} narration clips')
    late = [(s['id'], round(p[0] - s['video_start'], 2)) for s, p in zip(steps, placed) if p[0] - s['video_start'] > 1.0]
    if late:
        print('clips pushed later than their step (overlap avoided):', late)


if __name__ == '__main__':
    main()

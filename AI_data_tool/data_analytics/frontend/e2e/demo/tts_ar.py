"""Arabic narration clips for the Datalytics demo (edge-tts, Egyptian neural voices).

    python tts_ar.py samples            -> demo_output/narration/sample_<voice>.mp3 (both voices)
    python tts_ar.py clips              -> demo_output/narration/<step>.mp3 + durations.json

Reads frontend/e2e/demo/narration_ar.json (step id -> Arabic text; keys starting
with "_" are settings: _voice, _rate). A clip is only regenerated when its text,
voice or rate changed, so editing one line and re-running is quick.

Fallback: if edge-tts cannot reach the service, Windows' own speech engine
(System.Speech via PowerShell) is tried with any installed Arabic voice; the
script says so loudly, because those voices sound far less natural.
"""
import asyncio
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))      # .../data_analytics
OUT = os.path.join(ROOT, 'demo_output', 'narration')
VOICES = ['ar-EG-SalmaNeural', 'ar-EG-ShakirNeural']


def load():
    with open(os.path.join(HERE, 'narration_ar.json'), encoding='utf-8') as f:
        return json.load(f)


def mp3_seconds(path):
    """edge-tts writes constant-bitrate 48 kbit/s mono MP3, so size gives duration.
    (If ffprobe happens to be installed, it is asked instead.)"""
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', path], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return os.path.getsize(path) * 8 / 48000


async def edge(text, voice, rate, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(path)


def windows_fallback(text, path_wav):
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'ar*' } | Select-Object -First 1;"
        "if (-not $v) { Write-Error 'no Arabic Windows voice installed'; exit 2 };"
        "$s.SelectVoice($v.VoiceInfo.Name);"
        f"$s.SetOutputToWaveFile('{path_wav}');"
        "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
    )
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], input=text,
                       capture_output=True, text=True, encoding='utf-8')
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or 'Windows speech failed')


def synth(text, voice, rate, base):
    """Returns the written file path (mp3 from edge-tts, or wav from the fallback)."""
    mp3 = base + '.mp3'
    try:
        asyncio.run(edge(text, voice, rate, mp3))
        if os.path.getsize(mp3) > 0:
            return mp3
        raise RuntimeError('edge-tts returned no audio')
    except Exception as e:
        print(f'!! edge-tts failed ({e}); trying the Windows built-in Arabic voice instead', flush=True)
        wav = base + '.wav'
        windows_fallback(text, wav)
        return wav


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'clips'
    os.makedirs(OUT, exist_ok=True)
    n = load()
    if mode == 'samples':
        for v in VOICES:
            p = synth(n['_sample'], v, '+0%', os.path.join(OUT, f'sample_{v}'))
            print(f'sample {v}: {p} ({mp3_seconds(p):.1f}s)', flush=True)
        return
    voice, rate = n.get('_voice', VOICES[0]), n.get('_rate', '+0%')
    manifest_path = os.path.join(OUT, 'durations.json')
    old = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding='utf-8') as f:
            old = json.load(f)
    out = {}
    for key, text in n.items():
        if key.startswith('_'):
            continue
        sig = hashlib.sha1(f'{voice}|{rate}|{text}'.encode('utf-8')).hexdigest()
        prev = old.get(key)
        if prev and prev.get('sig') == sig and os.path.exists(prev['file']):
            out[key] = prev
            continue
        p = synth(text, voice, rate, os.path.join(OUT, key))
        out[key] = {'file': p, 'seconds': round(mp3_seconds(p), 3), 'sig': sig, 'text': text}
        print(f'{key:16s} {out[key]["seconds"]:5.1f}s', flush=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'{len(out)} clips, {sum(v["seconds"] for v in out.values()):.1f}s of narration, voice {voice}')


if __name__ == '__main__':
    main()

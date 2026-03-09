import sounddevice as sd
import numpy as np
import soundfile as sf
from queue import Queue

# Load a sample

BUFFER_SIZE = 2048
SR = 44100
pending = Queue()

active_samples = []  # list of (audio_array, current_position)

def load_sample(path):
    audio, sr = sf.read(path, dtype='float32')
    
    # Convert mono to stereo
    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=1)  # (n,) -> (n, 2)
    
    return audio, sr


clap, sr = load_sample("samples/TR-808 Kit/Clap.wav")
hihat, sr1 = load_sample("samples/TR-808 Kit/Hihat.wav")
kick, sr2 = load_sample("samples/TR-808 Kit/Kick Mid.wav")

def play_sample(audio):
    pending.put([audio, 0])  # safe to call from any thread

def callback(outdata, frames, time, status):
    mixed = np.zeros((frames, 2))

    while not pending.empty():
        active_samples.append(pending.get_nowait())
    
    for sample in active_samples:
        audio, pos = sample
        end = pos + frames
        chunk = audio[pos:end]
        mixed[:len(chunk)] += chunk
        sample[1] += frames  # advance position
    
    # Remove finished samples
    active_samples[:] = [s for s in active_samples if s[1] < len(s[0])]
    
    outdata[:] = np.clip(mixed, -1.0, 1.0)

stream = sd.OutputStream(
    samplerate=SR,
    blocksize=BUFFER_SIZE,
    channels=2,
    dtype='float32',
    callback=callback
)

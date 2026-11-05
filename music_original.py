"""Generate an original, gentle ambient instrumental; no copyrighted song samples."""
from __future__ import annotations
import math
import wave
from pathlib import Path
import numpy as np


def make_original_ambient(path, seconds=12, sr=22050):
    frames=int(seconds*sr)
    t=np.arange(frames,dtype=np.float64)/sr
    y=np.zeros(frames,dtype=np.float64)
    # Entirely new simple chord movement and a sparse, bell-like motif.
    chords=[(220,261.63,329.63),(196,246.94,293.66),(174.61,220,261.63)]
    block=seconds/len(chords)
    for ci,chord in enumerate(chords):
        start,end=ci*block,(ci+1)*block
        gate=(t>=start)&(t<end)
        local=t-start
        env=np.where(gate,np.minimum(1,np.maximum(0,local)/.9)*np.minimum(1,np.maximum(0,end-t)/1.4),0)
        for freq in chord:
            y+=.085*env*(np.sin(2*np.pi*freq*t)+.22*np.sin(2*np.pi*freq*2*t))
    notes=[(0.8,392), (2.5,440), (4.4,349.23), (6.8,329.63), (9.1,392)]
    for start,freq in notes:
        local=t-start; gate=(local>=0)&(local<2.3)
        env=np.where(gate, np.maximum(0,1-local/2.3)**2,0)
        y+=.055*env*(np.sin(2*np.pi*freq*t)+.24*np.sin(2*np.pi*freq*2.01*t))
    y*=np.minimum(1,t/1.1)*np.minimum(1,np.maximum(0,(seconds-t)/1.0))
    y=np.clip(y,-.8,.8)
    with wave.open(str(Path(path)),"wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes((y*32767).astype('<i2').tobytes())
    return Path(path)

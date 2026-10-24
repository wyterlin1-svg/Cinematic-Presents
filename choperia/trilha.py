"""Trilha sonora sintetizada (sem bancos de som): pad quente, notas de sino,
brasa crepitando, filete de chope, efervescência, mergulho e impacto final.
Saída: trilha.wav (48 kHz, estéreo). Uso: python3 trilha.py"""
import numpy as np
import wave

SR, DUR = 48000, 24.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(42)


def env(a, b, c, d):
    """envelope trapezoidal: sobe de a→b, desce de c→d"""
    return np.clip((t - a) / (b - a), 0, 1) * (1 - np.clip((t - c) / (d - c), 0, 1))


def lowpass(x, fc):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X / np.sqrt(1 + (f / fc) ** 4), len(x))


def bandpass(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X * ((f > lo) & (f < hi)), len(x))


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


L = np.zeros(N)
Rr = np.zeros(N)


def add(x, pan=0.0, gain=1.0):
    global L, Rr
    L += x * gain * np.sqrt((1 - pan) / 2)
    Rr += x * gain * np.sqrt((1 + pan) / 2)


# pad — Ré maior com 9ª, vozes levemente desafinadas, respiração lenta
for m, g in [(38, .9), (45, .7), (54, .45), (57, .4), (61, .3), (64, .28)]:
    for det, pan in [(-0.08, -.5), (0.08, .5)]:
        f = hz(m + det)
        ph = rng.uniform(0, 6.28)
        v = np.sin(2 * np.pi * f * t + ph) + .25 * np.sin(4 * np.pi * f * t + ph) + .1 * np.sin(6 * np.pi * f * t)
        breath = .75 + .25 * np.sin(2 * np.pi * .11 * t + ph)
        add(v * breath, pan, g * .045)
pad_env = env(0, 4, 13, 15.5) + .35 * env(15.5, 16.5, 17.2, 18.6) + env(18.6, 20.5, 23, 24)
L *= np.clip(pad_env, 0, 1.2)
Rr *= np.clip(pad_env, 0, 1.2)


def bell(at, midi, gain=.2, pan=0.0, decay=2.8):
    s = int(at * SR)
    tt = t[: N - s]
    f = hz(midi)
    v = (np.sin(2 * np.pi * f * tt) + .45 * np.sin(2 * np.pi * f * 2.0 * tt) * np.exp(-tt * 2)
         + .2 * np.sin(2 * np.pi * f * 3.01 * tt) * np.exp(-tt * 4))
    v *= np.exp(-tt / decay) * np.minimum(tt / .004, 1)
    x = np.zeros(N)
    x[s:] = v
    add(x, pan, gain)


# notas que marcam cada capítulo
bell(1.0, 74, .10, -.3)                        # o fio nasce
bell(4.5, 69, .16, -.2); bell(4.9, 76, .09, .3)  # I madeira
bell(9.7, 66, .16, .2); bell(10.1, 73, .09, -.3)  # II malte
bell(15.3, 71, .15, 0); bell(15.7, 78, .08, .4)   # III momento
for i, m in enumerate([62, 66, 69, 74]):          # assinatura — arpejo resolvendo
    bell(19.5 + i * .18, m, .14 - i * .015, -.4 + i * .27, 4)

# brasa crepitando (rusticidade): estalos esparsos, filtrados
crack = np.zeros(N)
for at in np.sort(rng.uniform(0, DUR, 260)):
    s = int(at * SR)
    ln = int(SR * rng.uniform(.002, .01))
    if s + ln < N:
        crack[s:s + ln] += rng.normal(0, 1, ln) * np.exp(-np.arange(ln) / (ln / 4)) * rng.uniform(.2, 1)
crack = bandpass(crack, 800, 6000)
add(crack * (env(0, 2, 6, 8) * .5 + env(18.8, 20, 23, 24)), rng.uniform(-.3, .3), .05)

# filete de chope + efervescência
pour = bandpass(rng.normal(0, 1, N), 300, 2400) * (1 + .3 * np.sin(2 * np.pi * 7 * t))
add(pour * env(8.9, 9.4, 11.4, 12.1), -.15, .05)
fizz = np.zeros(N)
idx = rng.choice(N, 9000, replace=False)
fizz[idx] = rng.normal(0, 1, len(idx))
fizz = bandpass(fizz, 4000, 14000)
fizz_env = env(9.4, 11, 13, 14) + 1.6 * env(13.5, 15, 16.8, 18.4)
add(fizz * fizz_env, .2, .4)

# mergulho no copo: varredura ascendente de ruído
sweep = rng.normal(0, 1, N)
sw = np.zeros(N)
for a, b, lo, hi in [(12.6, 13.4, 200, 600), (13.4, 14.2, 400, 1500), (14.2, 15.0, 900, 3500)]:
    seg = env(a, a + .3, b - .2, b + .3)
    sw += bandpass(sweep, lo, hi) * seg
add(sw, 0, .06)

# impacto suave da assinatura: grave + corpo
s = int(19.4 * SR)
tt = t[: N - s]
boom = (np.sin(2 * np.pi * 46 * tt * (1 + .4 * np.exp(-tt * 6))) * np.exp(-tt / 1.4)
        + .3 * lowpass(rng.normal(0, 1, len(tt)), 180) * np.exp(-tt / .35))
x = np.zeros(N)
x[s:] = boom * np.minimum(tt / .01, 1)
add(x, 0, .35)

# reverberação de sala de madeira (resposta ao impulso sintética)
ir_len = int(SR * 2.6)
ir_t = np.arange(ir_len) / SR
mix = []
for ch in (L, Rr):
    ir = rng.normal(0, 1, ir_len) * np.exp(-ir_t / .55)
    ir = lowpass(ir, 5000)
    ir[0] = 0
    wet = np.fft.irfft(np.fft.rfft(ch, N + ir_len) * np.fft.rfft(ir, N + ir_len))[:N]
    mix.append(ch + wet * (.18 / np.max(np.abs(wet)) * np.max(np.abs(ch))))
out = np.stack(mix, 1)
out *= np.clip(t / .6, 0, 1)[:, None] * np.clip((DUR - t) / .9, 0, 1)[:, None]
out *= .89 / np.max(np.abs(out))
out = np.tanh(out * 1.1) / np.tanh(1.1)

with wave.open('trilha.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((out * 32767).astype('<i2').tobytes())
print('trilha.wav ok')

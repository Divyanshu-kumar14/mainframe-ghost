// Web Audio synthesis: IBM beam-spring keystroke clicks and the S0C7 abend alarm.
// No samples are loaded; every sound is generated. The AudioContext is created on the
// first user gesture to satisfy browser autoplay policy.

type Ctx = AudioContext;

class TerminalAudio {
  private ctx: Ctx | null = null;
  private master: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private alarmUntil = 0;
  muted = false;

  private ensure(): Ctx | null {
    if (typeof window === 'undefined') return null;
    if (!this.ctx) {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) return null;
      this.ctx = new Ctor();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.55;
      this.master.connect(this.ctx.destination);
      this.noise = this.makeNoise(this.ctx);
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume();
    return this.ctx;
  }

  private makeNoise(ctx: Ctx): AudioBuffer {
    const length = Math.floor(ctx.sampleRate * 0.12);
    const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i += 1) data[i] = Math.random() * 2 - 1;
    return buffer;
  }

  /** Unlock audio from a click/keydown handler. */
  unlock(): void {
    this.ensure();
  }

  /**
   * Beam-spring keystroke: the buckling spring snaps against the capacitive pad
   * (bright noise transient), the heavy keycap bottoms out (low thock), and the
   * spring rings briefly (metallic partial). Pitch is jittered so repeats differ.
   */
  keystroke(heavy = false): void {
    const ctx = this.ensure();
    if (!ctx || !this.master || !this.noise || this.muted) return;
    const t = ctx.currentTime;
    const jitter = 0.9 + Math.random() * 0.2;

    // 1. snap transient
    const snap = ctx.createBufferSource();
    snap.buffer = this.noise;
    const snapFilter = ctx.createBiquadFilter();
    snapFilter.type = 'bandpass';
    snapFilter.frequency.value = 2600 * jitter;
    snapFilter.Q.value = 1.4;
    const snapGain = ctx.createGain();
    snapGain.gain.setValueAtTime(heavy ? 0.9 : 0.65, t);
    snapGain.gain.exponentialRampToValueAtTime(0.001, t + 0.028);
    snap.connect(snapFilter).connect(snapGain).connect(this.master);
    snap.start(t);
    snap.stop(t + 0.04);

    // 2. bottom-out thock
    const thock = ctx.createOscillator();
    thock.type = 'triangle';
    thock.frequency.setValueAtTime(190 * jitter, t + 0.004);
    thock.frequency.exponentialRampToValueAtTime(70, t + 0.05);
    const thockGain = ctx.createGain();
    thockGain.gain.setValueAtTime(0.0001, t);
    thockGain.gain.exponentialRampToValueAtTime(heavy ? 0.5 : 0.32, t + 0.006);
    thockGain.gain.exponentialRampToValueAtTime(0.001, t + 0.07);
    thock.connect(thockGain).connect(this.master);
    thock.start(t);
    thock.stop(t + 0.08);

    // 3. spring ring
    const ring = ctx.createOscillator();
    ring.type = 'sine';
    ring.frequency.value = 3300 * jitter;
    const ringGain = ctx.createGain();
    ringGain.gain.setValueAtTime(0.045, t + 0.003);
    ringGain.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
    ring.connect(ringGain).connect(this.master);
    ring.start(t);
    ring.stop(t + 0.1);
  }

  /** S0C7 abend klaxon: alternating 880/440 Hz square through a lowpass, ~1.6 s. */
  abendAlarm(): void {
    const ctx = this.ensure();
    if (!ctx || !this.master || this.muted) return;
    const t = ctx.currentTime;
    if (t < this.alarmUntil) return; // never stack alarms
    const duration = 1.6;
    this.alarmUntil = t + duration;

    const osc = ctx.createOscillator();
    osc.type = 'square';
    const step = 0.2;
    for (let i = 0; i * step < duration; i += 1) {
      osc.frequency.setValueAtTime(i % 2 === 0 ? 880 : 440, t + i * step);
    }
    const lowpass = ctx.createBiquadFilter();
    lowpass.type = 'lowpass';
    lowpass.frequency.value = 2400;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
    gain.gain.setValueAtTime(0.22, t + duration - 0.25);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
    osc.connect(lowpass).connect(gain).connect(this.master);
    osc.start(t);
    osc.stop(t + duration + 0.05);
  }

  /** Short rising chirp for a passing hook (exit 0). */
  passChime(): void {
    const ctx = this.ensure();
    if (!ctx || !this.master || this.muted) return;
    const t = ctx.currentTime;
    [660, 990].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = freq;
      const gain = ctx.createGain();
      const start = t + i * 0.09;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.16, start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.18);
      osc.connect(gain).connect(this.master!);
      osc.start(start);
      osc.stop(start + 0.2);
    });
  }
}

export const terminalAudio = new TerminalAudio();

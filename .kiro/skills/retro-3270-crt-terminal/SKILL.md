---
name: retro-3270-crt-terminal
description: Design and implementation patterns for building authentic retro IBM 3270 CRT terminal user interfaces in React 19, Tailwind CSS, and Web Audio API. Covers P31 green / P4 amber phosphor color palettes, CRT scanlines, screen curvature shaders, phosphor decay persistence, and mechanical acoustic key click synthesis. Use when building retro-futuristic, spooky, or vintage terminal cockpits such as the MainframeGhost 3270 cockpit.
---

# Retro IBM 3270 CRT Ghost Terminal Skill

This skill provides production design patterns for building an authentic, spooky IBM 3270 CRT Ghost Terminal in React 19, Vite, and Tailwind CSS.

---

## 1. Phosphor Color Palettes

### IBM 3270 P31 Green Phosphor (Classic Mainframe)
- Primary Glow Text: `#33ff33` (`rgb(51, 255, 51)`)
- Muted Character Dim: `#1f8a1f`
- Dark Terminal Background: `#051405`
- High Intensity Highlight: `#66ff66`
- S0C7 Abend Red: `#ff3333`

### IBM 3279 P4 Amber Phosphor (Ergonomic Night Mode)
- Primary Glow Text: `#ffb000` (`rgb(255, 176, 0)`)
- Muted Character Dim: `#996a00`
- Dark Terminal Background: `#140d02`
- High Intensity Highlight: `#ffd04d`

---

## 2. CRT Screen Effects & Tailwind Shaders

### Custom CSS Scanlines & Phosphor Bloom
```css
/* CRT Scanline Overlay */
.crt-scanlines {
  background: linear-gradient(
    rgba(18, 16, 16, 0) 50%, 
    rgba(0, 0, 0, 0.4) 50%
  ), 
  linear-gradient(
    90deg,
    rgba(255, 0, 0, 0.03),
    rgba(0, 255, 0, 0.01),
    rgba(0, 0, 255, 0.03)
  );
  background-size: 100% 3px, 6px 100%;
  pointer-events: none;
}

/* CRT Glass Vignette & Barrel Curvature */
.crt-vignette {
  box-shadow: inset 0 0 80px rgba(0, 0, 0, 0.85);
}

/* Phosphor Glow Drop Shadow */
.phosphor-text {
  text-shadow: 0 0 4px rgba(51, 255, 51, 0.7), 0 0 10px rgba(51, 255, 51, 0.4);
}

.amber-text {
  text-shadow: 0 0 4px rgba(255, 176, 0, 0.7), 0 0 10px rgba(255, 176, 0, 0.4);
}

/* Subtle CRT Flicker */
@keyframes crt-flicker {
  0% { opacity: 0.985; }
  50% { opacity: 1; }
  100% { opacity: 0.988; }
}

.animate-flicker {
  animation: crt-flicker 0.15s infinite;
}
```

---

## 3. Web Audio API Acoustic Feedback (IBM Beam-Spring Keystroke)

Real IBM 3270 and 3278 terminals used heavy solenoid clickers to provide tactile feedback to typists.

```typescript
class TerminalAudioEngine {
  private ctx: AudioContext | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      this.ctx = new AudioCtx();
    }
  }

  playKeystroke() {
    if (!this.ctx) return;
    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    osc.type = 'triangle';
    osc.frequency.setValueAtTime(320, this.ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(80, this.ctx.currentTime + 0.04);

    gain.gain.setValueAtTime(0.2, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.04);

    osc.connect(gain);
    gain.connect(this.ctx.destination);

    osc.start();
    osc.stop(this.ctx.currentTime + 0.04);
  }

  playAbendAlarm() {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();

    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(880, this.ctx.currentTime);
    osc.frequency.setValueAtTime(440, this.ctx.currentTime + 0.15);

    gain.gain.setValueAtTime(0.3, this.ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.4);

    osc.connect(gain);
    gain.connect(this.ctx.destination);

    osc.start();
    osc.stop(this.ctx.currentTime + 0.4);
  }
}

export const terminalAudio = new TerminalAudioEngine();
```

---

## 4. 80x24 IBM 3270 Status Line & Hex Dump Grid

The bottom row of an IBM 3270 screen is always the operator information area (OIA):
```
4A 00 12 34 56 78 9D | PIC S9(7)V99 COMP-3 | VALUE: -1234567.89
--------------------------------------------------------------------------------
SYSTEM READY   [z/OS V2.5]   SEC: RACF-L4   LPAR: PROD01   OIA: NUMA [CONNECTED]
```
Ensure the UI renders monospace fonts (`Courier New`, `IBM Plex Mono`, or `VT323`) to maintain the strict 80-column grid alignment.

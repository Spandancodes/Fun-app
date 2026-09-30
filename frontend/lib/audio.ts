export const AUDIO = {
  no_first: "/audio/no_first.mp3",
} as const;
export type Slot = keyof typeof AUDIO;
export class AudioController {
  private clips = new Map<Slot, HTMLAudioElement>();
  private reportedFailures = new Set<Slot>();
  private active?: HTMLAudioElement;
  private timer?: ReturnType<typeof setTimeout>;
  private generation = 0;
  muted = false;
  volume = 0.65;
  private reportFailure(slot: Slot) {
    if (this.reportedFailures.has(slot)) return;
    this.reportedFailures.add(slot);
    console.warn(`Missing or unreadable audio for ${slot}: ${AUDIO[slot]}`);
  }
  private clip(slot: Slot) {
    const existing = this.clips.get(slot);
    if (existing) return existing;
    const clip = new Audio(AUDIO[slot]);
    clip.preload = "auto";
    clip.addEventListener("error", () => {
      if (this.active === clip) this.reportFailure(slot);
    });
    this.clips.set(slot, clip);
    return clip;
  }
  stop() {
    this.generation++;
    clearTimeout(this.timer);
    if (this.active) {
      this.active.pause();
      this.active.currentTime = 0;
    }
    this.active = undefined;
  }
  setMuted(value: boolean) {
    this.muted = value;
    if (value) this.stop();
  }
  setVolume(value: number) {
    this.volume = Math.max(0, Math.min(1, value));
    if (this.active) this.active.volume = this.volume;
  }
  async play(slot: Slot) {
    this.stop();
    if (this.muted) return;
    const clip = this.clip(slot);
    const generation = this.generation;
    this.active = clip;
    clip.volume = this.volume;
    this.timer = setTimeout(() => this.stop(), 12000);
    try {
      await clip.play();
      this.reportedFailures.delete(slot);
    } catch (error) {
      if (this.active !== clip || generation !== this.generation) return;
      if (error instanceof DOMException && error.name === "NotAllowedError")
        console.warn(`Browser blocked audio playback for ${slot}`);
      else if (error instanceof DOMException && error.name === "AbortError")
        return;
      else this.reportFailure(slot);
    }
  }
  dispose() {
    this.stop();
    this.clips.forEach((clip) => {
      clip.removeAttribute("src");
      clip.load();
    });
    this.clips.clear();
    this.reportedFailures.clear();
  }
}

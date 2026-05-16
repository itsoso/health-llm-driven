export type AudioStatusLike = {
  didJustFinish?: boolean;
  finished?: boolean;
  playbackState?: string;
  currentTime?: number;
  duration?: number;
  playing?: boolean;
};

export function shouldFinishAudioPlayback(status: AudioStatusLike | null | undefined): boolean {
  if (!status) return false;
  if (status.didJustFinish || status.finished) return true;
  const playbackState = String(status.playbackState || '').toLowerCase();
  if (['ended', 'finished', 'completed'].includes(playbackState)) return true;

  const current = Number(status.currentTime);
  const duration = Number(status.duration);
  if (Number.isFinite(current) && Number.isFinite(duration) && duration > 0) {
    return current >= duration - 0.08 && status.playing !== true;
  }
  return false;
}

export function estimateTtsFallbackMs(text: string, durationSeconds?: number): number {
  const duration = Number(durationSeconds);
  if (Number.isFinite(duration) && duration > 0) {
    return Math.min(90000, Math.max(8000, Math.ceil(duration * 1000) + 5000));
  }
  return Math.max(8000, Math.min(60000, text.length * 280 + 8000));
}

import { reactive } from "vue";

const defaultVolume = 55;

export const settingsState = reactive({
  bgm: localStorage.getItem("gomoku_bgm") === "on",
  sound: localStorage.getItem("gomoku_sound") !== "off",
  chatSound: localStorage.getItem("gomoku_chat_sound") !== "off",
  volume: Number(localStorage.getItem("gomoku_volume") || defaultVolume),
});

let audioContext: AudioContext | null = null;
let bgmTimer: number | null = null;
let noteIndex = 0;

function getAudioContext() {
  const AudioCtor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtor) return null;
  if (!audioContext) audioContext = new AudioCtor();
  if (audioContext.state === "suspended") void audioContext.resume();
  return audioContext;
}

function gainValue(scale = 1) {
  return Math.max(0, Math.min(1, settingsState.volume / 100)) * scale;
}

function playTone(frequency: number, duration: number, scale = 1) {
  const ctx = getAudioContext();
  if (!ctx) return;
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = "sine";
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, gainValue(scale)), ctx.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
  oscillator.connect(gain);
  gain.connect(ctx.destination);
  oscillator.start();
  oscillator.stop(ctx.currentTime + duration + 0.02);
}

function persist() {
  localStorage.setItem("gomoku_bgm", settingsState.bgm ? "on" : "off");
  localStorage.setItem("gomoku_sound", settingsState.sound ? "on" : "off");
  localStorage.setItem("gomoku_chat_sound", settingsState.chatSound ? "on" : "off");
  localStorage.setItem("gomoku_volume", String(settingsState.volume));
}

export function setBgm(enabled: boolean) {
  settingsState.bgm = enabled;
  persist();
  if (enabled) startBgm();
  else stopBgm();
}

export function setSound(enabled: boolean) {
  settingsState.sound = enabled;
  persist();
}

export function setChatSound(enabled: boolean) {
  settingsState.chatSound = enabled;
  persist();
}

export function setVolume(volume: number) {
  settingsState.volume = Math.max(0, Math.min(100, volume));
  persist();
}

export function playStoneSound() {
  if (!settingsState.sound) return;
  playTone(520, 0.07, 0.18);
  window.setTimeout(() => playTone(280, 0.09, 0.12), 35);
}

export function playChatSound() {
  if (!settingsState.chatSound) return;
  playTone(680, 0.1, 0.34);
  window.setTimeout(() => playTone(940, 0.12, 0.28), 60);
}

export function playGameStartSound() {
  if (!settingsState.sound) return;
  playTone(392, 0.12, 0.22);
  window.setTimeout(() => playTone(523.25, 0.14, 0.24), 90);
  window.setTimeout(() => playTone(659.25, 0.18, 0.22), 190);
}

export function playGameEndSound() {
  if (!settingsState.sound) return;
  playTone(784, 0.14, 0.25);
  window.setTimeout(() => playTone(587.33, 0.18, 0.24), 130);
  window.setTimeout(() => playTone(392, 0.24, 0.2), 280);
}

export function playCountdownSound() {
  if (!settingsState.sound) return;
  playTone(1046.5, 0.08, 0.32);
}

export function startBgm() {
  if (!settingsState.bgm || bgmTimer !== null) return;
  const notes = [196, 246.94, 293.66, 246.94, 220, 196, 164.81, 196];
  playTone(notes[noteIndex % notes.length], 0.38, 0.055);
  bgmTimer = window.setInterval(() => {
    noteIndex += 1;
    playTone(notes[noteIndex % notes.length], 0.42, 0.05);
  }, 900);
}

export function stopBgm() {
  if (bgmTimer === null) return;
  window.clearInterval(bgmTimer);
  bgmTimer = null;
}

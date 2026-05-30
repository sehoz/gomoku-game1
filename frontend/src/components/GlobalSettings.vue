<script setup lang="ts">
import { ref } from "vue";
import { Music, Settings, Volume2 } from "lucide-vue-next";
import Modal from "./Modal.vue";
import { setBgm, setSound, setVolume, settingsState } from "../stores/settings";

const open = ref(false);

function onBgmChange(event: Event) {
  setBgm((event.target as HTMLInputElement).checked);
}

function onSoundChange(event: Event) {
  setSound((event.target as HTMLInputElement).checked);
}

function onVolumeChange(event: Event) {
  setVolume(Number((event.target as HTMLInputElement).value));
}
</script>

<template>
  <button class="global-settings-button" type="button" @click="open = true"><Settings :size="20" /><span>设置</span></button>
  <Modal v-if="open" title="全局设置" @close="open = false">
    <div class="settings-form">
      <label class="switch-row"><span><Music :size="18" />背景音乐</span><input :checked="settingsState.bgm" type="checkbox" @change="onBgmChange" /></label>
      <label class="slider-row"><span><Volume2 :size="18" />音乐音量</span><input :value="settingsState.volume" min="0" max="100" type="range" @input="onVolumeChange" /><strong>{{ settingsState.volume }}%</strong></label>
      <label class="switch-row"><span><Volume2 :size="18" />落子音效</span><input :checked="settingsState.sound" type="checkbox" @change="onSoundChange" /></label>
    </div>
  </Modal>
</template>

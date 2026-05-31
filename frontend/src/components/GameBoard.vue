<script setup lang="ts">
import { computed, ref } from "vue";
import type { Move } from "../types";

const props = defineProps<{ size?: number; stones: Move[]; interactive?: boolean; showMoveNumbers?: boolean }>();
const emit = defineEmits<{ play: [x: number, y: number] }>();
const boardSize = computed(() => props.size || 15);
const step = computed(() => 100 / (boardSize.value - 1));
const hoverPoint = ref<{ x: number; y: number } | null>(null);
const hitRadiusRatio = 0.42;
const starPoints = computed(() => {
  if (boardSize.value !== 15) return [];
  return [
    { x: 3, y: 3 },
    { x: 11, y: 3 },
    { x: 7, y: 7 },
    { x: 3, y: 11 },
    { x: 11, y: 11 },
  ];
});

function stoneAt(x: number, y: number) {
  return props.stones.find((stone) => stone.x === x && stone.y === y);
}

function isLastStone(x: number, y: number) {
  const last = props.stones[props.stones.length - 1];
  return Boolean(last && last.x === x && last.y === y);
}

function moveNumber(x: number, y: number) {
  const index = props.stones.findIndex((stone) => stone.x === x && stone.y === y);
  if (index < 0) return "";
  return props.stones[index].move_number || index + 1;
}

function pointFromEvent(event: PointerEvent | MouseEvent) {
  const target = event.currentTarget as HTMLElement | null;
  if (!target) return null;
  const grid = target.querySelector(".board-grid") as HTMLElement | null;
  if (!grid) return null;
  const rect = grid.getBoundingClientRect();
  const cell = rect.width / (boardSize.value - 1);
  const rawX = (event.clientX - rect.left) / cell;
  const rawY = (event.clientY - rect.top) / cell;
  const x = Math.round(rawX);
  const y = Math.round(rawY);
  if (x < 0 || y < 0 || x >= boardSize.value || y >= boardSize.value) return null;
  const distance = Math.hypot(rawX - x, rawY - y) * cell;
  if (distance > cell * hitRadiusRatio) return null;
  return { x, y };
}

function canPlayAt(point: { x: number; y: number } | null) {
  return Boolean(props.interactive && point && !stoneAt(point.x, point.y));
}

function updateHover(event: PointerEvent) {
  const point = pointFromEvent(event);
  hoverPoint.value = canPlayAt(point) ? point : null;
}

function clearHover() {
  hoverPoint.value = null;
}

function playFromBoard(event: MouseEvent) {
  const point = pointFromEvent(event);
  if (!canPlayAt(point) || !point) return;
  emit("play", point.x, point.y);
}
</script>

<template>
  <div class="board-shell">
    <div :class="['board-hit-area', { 'board-can-play': hoverPoint }]" @click="playFromBoard" @pointerleave="clearHover" @pointermove="updateHover">
      <div class="board-grid" :style="{ backgroundSize: `${step}% ${step}%`, '--board-step': `${step}%` }">
        <span
          v-for="point in starPoints"
          :key="`${point.x}-${point.y}`"
          class="board-star"
          :style="{ left: `${point.x * step}%`, top: `${point.y * step}%` }"
          aria-hidden="true"
        />
        <span
          v-for="index in boardSize * boardSize"
          :key="index"
          class="board-point"
          :style="{ left: `${((index - 1) % boardSize) * step}%`, top: `${Math.floor((index - 1) / boardSize) * step}%` }"
        >
          <span
            v-if="stoneAt((index - 1) % boardSize, Math.floor((index - 1) / boardSize))"
            :class="[
              'stone',
              { 'stone-numbered': showMoveNumbers },
              `stone-${stoneAt((index - 1) % boardSize, Math.floor((index - 1) / boardSize))?.color}`,
              { 'stone-last': isLastStone((index - 1) % boardSize, Math.floor((index - 1) / boardSize)) },
            ]"
          >{{ showMoveNumbers ? moveNumber((index - 1) % boardSize, Math.floor((index - 1) / boardSize)) : "" }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

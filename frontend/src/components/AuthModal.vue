<script setup lang="ts">
import { ref } from "vue";
import { LogIn } from "lucide-vue-next";
import Modal from "./Modal.vue";
import { login, register } from "../stores/auth";

const emit = defineEmits<{ close: [] }>();
const mode = ref<"login" | "register">("login");
const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function submit() {
  error.value = "";
  const cleanUsername = username.value.trim();
  if (!cleanUsername) {
    error.value = "请输入用户名";
    return;
  }
  if (password.value.length < 6) {
    error.value = "密码至少需要 6 位";
    return;
  }
  submitting.value = true;
  try {
    if (mode.value === "login") await login(cleanUsername, password.value);
    else await register(cleanUsername, password.value);
    emit("close");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "操作失败";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal :title="mode === 'login' ? '登录账号' : '注册账号'" @close="emit('close')">
    <form class="modal-form" @submit.prevent="submit">
      <div class="auth-tabs">
        <button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>
      <label>用户名<input v-model="username" autocomplete="username" placeholder="输入用户名" /></label>
      <label>密码<input v-model="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" type="password" placeholder="至少 6 位" /></label>
      <p v-if="error" class="form-error">{{ error }}</p>
      <button class="primary-button" :disabled="submitting" type="submit"><LogIn :size="18" />{{ submitting ? "处理中" : mode === "login" ? "登录" : "注册" }}</button>
    </form>
  </Modal>
</template>

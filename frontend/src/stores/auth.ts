import { reactive } from "vue";
import { api } from "../api";
import type { UserProfile } from "../types";

export const authState = reactive({
  user: null as UserProfile | null,
  ready: false,
});

export const isAuthenticated = () => Boolean(authState.user);

export async function initAuth() {
  if (!localStorage.getItem("gomoku_token")) {
    authState.ready = true;
    return;
  }
  try {
    const data = await api.me();
    authState.user = data.user;
  } catch {
    localStorage.removeItem("gomoku_token");
    authState.user = null;
  } finally {
    authState.ready = true;
  }
}

export async function login(username: string, password: string) {
  const data = await api.login(username, password);
  localStorage.setItem("gomoku_token", data.token);
  authState.user = data.user;
}

export async function register(username: string, password: string, email = "") {
  const data = await api.register(username, password, email);
  localStorage.setItem("gomoku_token", data.token);
  authState.user = data.user;
}

export async function logout() {
  try {
    if (localStorage.getItem("gomoku_token")) await api.logout();
  } finally {
    localStorage.removeItem("gomoku_token");
    authState.user = null;
  }
}

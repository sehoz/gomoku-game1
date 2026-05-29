import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import HomeView from "./views/HomeView.vue";
import SoloView from "./views/SoloView.vue";
import RoomsView from "./views/RoomsView.vue";
import RoomView from "./views/RoomView.vue";
import ProfileView from "./views/ProfileView.vue";
import "./styles.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: HomeView },
    { path: "/solo", component: SoloView },
    { path: "/rooms", component: RoomsView },
    { path: "/rooms/:id", component: RoomView },
    { path: "/profile", component: ProfileView },
  ],
});

createApp(App).use(router).mount("#app");

import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";

type ErrorWindow = Window & { __errors?: string[] };
const errorWindow = window as ErrorWindow;
errorWindow.__errors = [];
window.addEventListener("error", (event) => {
  errorWindow.__errors?.push(String(event.message || event.error || "unknown error"));
});
window.addEventListener("unhandledrejection", (event) => {
  errorWindow.__errors?.push(String(event.reason || "unhandled rejection"));
});

createApp(App).mount("#app");

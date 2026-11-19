import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { navegador } from "../sesion/almacen.js";

/* jsdom no navega: las salidas a otra página se anotan. */
beforeEach(() => {
  vi.spyOn(navegador, "ir").mockImplementation(() => {});
  vi.spyOn(navegador, "reemplazar").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.documentElement.removeAttribute("data-tema");
  document.body.className = "";
});

import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { configureApiClient } from "../api/client";
import { browser } from "../lib/browser";

// jsdom may lack the modal dialog API used by <Modal>.
if (
  typeof HTMLDialogElement !== "undefined" &&
  !HTMLDialogElement.prototype.showModal
) {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close() {
    this.open = false;
  };
}

beforeEach(() => {
  // Full-page navigations (login, logout) are recorded instead of performed.
  vi.spyOn(browser, "assign").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  configureApiClient({});
  sessionStorage.clear();
});

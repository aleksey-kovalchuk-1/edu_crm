import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

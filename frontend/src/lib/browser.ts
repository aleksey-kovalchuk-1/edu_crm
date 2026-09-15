/**
 * Full-page navigation, wrapped so tests can replace it (jsdom's
 * window.location.assign cannot be redefined).
 */
export const browser = {
  assign(url: string) {
    window.location.assign(url);
  },
};

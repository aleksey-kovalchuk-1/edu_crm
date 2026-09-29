// Scales the reCAPTCHA widget (a fixed 304 x 78 iframe) so it is exactly as wide as the «Фамилия» field.
// The wrapper is pinned to the widget's own width first, so after scaling it is no wider than the field.
// (Renamed from captcha-fit.js: browsers keep theme files for 30 days, so a changed file needs a new name.)
(function () {
  var WIDTH = 304;
  var HEIGHT = 78;

  function fit() {
    var box = document.querySelector(".unicrm-captcha .g-recaptcha");
    if (!box) return;
    var field = document.getElementById("lastName") || document.querySelector("#kc-register-form input[type=text]");
    var width = (field || box.parentElement).getBoundingClientRect().width;
    if (!width) return;
    var scale = width / WIDTH;
    box.style.width = WIDTH + "px";
    box.style.transform = "scale(" + scale + ")";
    box.style.transformOrigin = "0 0";
    box.parentElement.style.height = Math.ceil(HEIGHT * scale) + "px";
  }

  window.addEventListener("load", fit);
  window.addEventListener("resize", fit);
  document.addEventListener("DOMContentLoaded", fit);
})();

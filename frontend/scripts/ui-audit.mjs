// frontend/scripts/ui-audit.mjs
// Layout audit for the isolated verification stack (never production). Passwords are read from a
// file and never printed.
import { chromium } from "playwright-core";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";

const { values: args } = parseArgs({
  options: {
    role: { type: "string" },
    pages: { type: "string" },
    sizes: { type: "string", default: "1440x900,1280x600,1024x768,768x1024,375x812" },
    out: { type: "string" },
  },
});
const LOGINS = { super: "irina_super_admin", admin: "admin_1", manager: "manager_1" };
const base = process.env.AUDIT_BASE ?? "http://localhost:18080";
const login = LOGINS[args.role];
if (!login || !args.pages || !args.out || !process.env.AUDIT_ACCOUNTS) {
  console.error("usage: AUDIT_ACCOUNTS=file npm run audit:ui -- --role super|admin|manager --pages /,/tasks --out dir");
  process.exit(2);
}
const accounts = Object.fromEntries(
  readFileSync(process.env.AUDIT_ACCOUNTS, "utf8").trim().split("\n").map((l) => l.split(/=(.*)/s).slice(0, 2)),
);
mkdirSync(`${args.out}/shots`, { recursive: true });

function measure() {
  const vw = innerWidth;
  const lum = (c) => {
    const m = c.match(/[\d.]+/g);
    if (!m) return null;
    const [r, g, b, a = 1] = m.map(Number);
    const l = [r, g, b].map((v) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return { l: 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2], a };
  };
  const bgOf = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const L = lum(getComputedStyle(e).backgroundColor);
      if (L && L.a > 0.9) return L.l;
    }
    return 1;
  };
  const texts = [...document.querySelectorAll("body *")].filter(
    (e) => e.offsetParent !== null && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()),
  );
  const small = [];
  const lowContrast = [];
  for (const e of texts) {
    const cs = getComputedStyle(e);
    const size = parseFloat(cs.fontSize);
    if (size < 12) small.push(`${size}px «${e.textContent.trim().slice(0, 30)}»`);
    const fg = lum(cs.color);
    if (!fg || fg.a < 0.9) continue;
    const bg = bgOf(e);
    const ratio = (Math.max(fg.l, bg) + 0.05) / (Math.min(fg.l, bg) + 0.05);
    const large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
    if (ratio < (large ? 3 : 4.5)) lowContrast.push(`${ratio.toFixed(2)} ${size}px «${e.textContent.trim().slice(0, 30)}»`);
  }
  const controls = [...document.querySelectorAll("a[href], button, input, select, textarea, [role=button]")].filter(
    (e) => e.offsetParent !== null && !e.closest("label"),
  );
  const tiny = controls
    .map((e) => [e, e.getBoundingClientRect()])
    .filter(([, r]) => r.width > 0 && (r.width < 44 || r.height < 44))
    .map(([e, r]) => `${e.tagName.toLowerCase()} ${Math.round(r.width)}×${Math.round(r.height)} «${(e.getAttribute("aria-label") || e.textContent || "").trim().slice(0, 24)}»`);
  const menu = document.querySelector(".sidebar");
  let menuReach = null;
  if (menu && getComputedStyle(menu).visibility !== "hidden" && menu.getBoundingClientRect().right > 0) {
    menu.scrollTop = menu.scrollHeight;
    const last = [...menu.querySelectorAll("a, button")].at(-1)?.getBoundingClientRect();
    menuReach = !!last && last.bottom <= innerHeight + 1;
  }
  return {
    pageOverflowX: document.documentElement.scrollWidth > vw,
    small: [...new Set(small)].slice(0, 10),
    lowContrast: [...new Set(lowContrast)].slice(0, 10),
    tiny: vw < 768 ? tiny.slice(0, 10) : [],
    menuReach,
    h1: document.querySelector("h1")?.textContent ?? null,
  };
}

const browser = await chromium.launch({ channel: "chrome" });
const page = await (await browser.newContext({ locale: "ru-RU" })).newPage();
await page.goto(`${base}/`);
await page.waitForSelector("#username", { timeout: 30000 });
await page.fill("#username", login);
await page.fill("#password", accounts[`${login.toUpperCase()}_PASSWORD`]);
await Promise.all([page.waitForURL((u) => !u.pathname.startsWith("/auth"), { timeout: 30000 }), page.click("#kc-login")]);

const report = {};
let failed = false;
for (const size of args.sizes.split(",")) {
  const [width, height] = size.split("x").map(Number);
  await page.setViewportSize({ width, height });
  for (const path of args.pages.split(",")) {
    const name = `${args.role}-${path === "/" ? "overview" : path.slice(1).replaceAll("/", "_")}-${size}`;
    await page.goto(`${base}${path}`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${args.out}/shots/${name}.png`, fullPage: true });
    const m = await page.evaluate(measure);
    report[name] = m;
    if (m.pageOverflowX || m.small.length || m.tiny.length || m.menuReach === false) failed = true;
  }
}
writeFileSync(`${args.out}/metrics-${args.role}.json`, JSON.stringify(report, null, 1));
await browser.close();
console.log(`${Object.keys(report).length} captures; ${failed ? "FAILURES — see metrics" : "all checks passed"}`);
process.exit(failed ? 1 : 0);

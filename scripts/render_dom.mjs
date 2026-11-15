// Rendert eine Seite in headless Chrome und gibt das DOM aus, sobald body[data-ready] gesetzt ist
// (oder ein Ladefehler angezeigt wird). Wird von scripts/check_site.py aufgerufen.
// Aufruf: node scripts/render_dom.mjs <url>     Braucht Node >= 22 (globales WebSocket) und Chrome.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const url = process.argv[2];
const chromePath = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = mkdtempSync(join(tmpdir(), "odqw-chrome-"));
const port = 9300 + Math.floor(Math.random() * 600);
const chrome = spawn(chromePath, ["--headless=new", "--disable-gpu", "--no-first-run",
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function finish(code, text) {
  if (text) process.stdout.write(text);
  chrome.kill();
  setTimeout(() => { rmSync(profile, { recursive: true, force: true }); process.exit(code); }, 300);
}

let targets;
for (let i = 0; i < 50 && !targets; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
}
if (!targets) { console.error("Chrome nicht erreichbar"); finish(2); }

const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
let nextId = 0;
const pending = new Map();
function send(method, params = {}) {
  const id = ++nextId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve) => pending.set(id, resolve));
}
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.method === "Runtime.exceptionThrown") console.error("JS-Fehler:", d.params.exceptionDetails.exception?.description);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); }
};
ws.onopen = async () => {
  await send("Runtime.enable");
  await send("Page.navigate", { url });
  for (let i = 0; i < 120; i++) {
    const r = await send("Runtime.evaluate", { expression:
      "document.body && (document.body.dataset.ready === 'true' || !document.getElementById('ladefehler').hidden)" });
    if (r?.result?.value === true) break;
    await sleep(250);
  }
  const html = await send("Runtime.evaluate", { expression: "document.documentElement.outerHTML" });
  finish(0, html.result.value);
};

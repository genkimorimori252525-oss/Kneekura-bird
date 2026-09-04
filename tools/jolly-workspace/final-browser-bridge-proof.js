"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawn, spawnSync} = require("node:child_process");

const sourceRoot = path.resolve(process.argv[2] || "");
const outputRoot = path.resolve(process.argv[3] || path.join(os.tmpdir(), "jolly-browser-bridge-proof"));
if (!fs.existsSync(sourceRoot)) throw new Error("candidate source root is missing");
fs.mkdirSync(outputRoot, {recursive:true});

const {launch} = require(path.join(sourceRoot, "workspace", "production", "src", "launcher.js"));

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function request(endpoint, pathname, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.body !== undefined && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(endpoint + pathname, {
    method:options.method || "GET",
    headers,
    body:options.body === undefined ? undefined : JSON.stringify(options.body),
    cache:"no-store"
  });
  let body = null;
  try { body = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(`${options.method || "GET"} ${pathname} -> ${response.status}: ${body && body.error || "unknown"}`);
  return body;
}

function findChrome() {
  const candidates = [
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google", "Chrome", "Application", "chrome.exe"),
    process.env["PROGRAMFILES(X86)"] && path.join(process.env["PROGRAMFILES(X86)"], "Google", "Chrome", "Application", "chrome.exe"),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe")
  ].filter(Boolean);
  return candidates.find(candidate => fs.existsSync(candidate)) || null;
}

async function heartbeat(endpoint, previousNonce = null) {
  await request(endpoint, "/api/browser-bridge/select-project", {method:"POST", body:{projectId:"alpha"}});
  const origin = "chrome-extension://" + "a".repeat(32);
  const paired = await request(endpoint, "/api/browser-bridge/heartbeat", {
    method:"POST",
    headers:{Origin:origin},
    body:{conversationPath:"/c/windows-final-proof", panelVisibility:"HIDDEN"}
  });
  assert.equal(paired.paired, true);
  assert.equal(paired.lease.projectId, "alpha");
  assert.equal(paired.lease.conversationPath, "/c/windows-final-proof");
  assert.match(paired.lease.nonce, /^[A-Za-z0-9._-]{8,160}$/);
  if (previousNonce) assert.notEqual(paired.lease.nonce, previousNonce, "Browser Companion reconnect must receive a new lease nonce");
  const status = (await request(endpoint, "/api/browser-bridge/status")).status;
  assert.equal(status.workspaceLeaseActive, true);
  assert.equal(status.heartbeatFresh, true);
  assert.equal(status.panelVisibility, "HIDDEN");
  return paired.lease;
}

async function waitForFile(file, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(file) && fs.statSync(file).size > 0) return;
    await sleep(100);
  }
  throw new Error(`timed out waiting for ${file}`);
}

async function closeChrome(child) {
  if (!child || child.exitCode !== null) return;
  try {
    if (process.platform === "win32") spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {windowsHide:true, stdio:"ignore"});
    else child.kill("SIGKILL");
  } catch (_) {}
}

async function connectCdp(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP websocket open timeout")), 5000);
    ws.addEventListener("open", () => { clearTimeout(timer); resolve(); }, {once:true});
    ws.addEventListener("error", () => { clearTimeout(timer); reject(new Error("CDP websocket error")); }, {once:true});
  });
  let nextId = 1;
  const pending = new Map();
  ws.addEventListener("message", event => {
    let message;
    try { message = JSON.parse(String(event.data)); } catch (_) { return; }
    if (!message.id || !pending.has(message.id)) return;
    const entry = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) entry.reject(new Error(JSON.stringify(message.error)));
    else entry.resolve(message.result || {});
  });
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, {resolve, reject});
    ws.send(JSON.stringify({id, method, params}));
    setTimeout(() => {
      if (!pending.has(id)) return;
      pending.delete(id);
      reject(new Error(`CDP timeout: ${method}`));
    }, 10000);
  });
  return {ws, call};
}

async function renderProof(endpoint) {
  const chrome = findChrome();
  assert.ok(chrome, "Google Chrome is required for rendered Browser Companion proof");
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "jolly-browser-proof-cdp-"));
  const portFile = path.join(profile, "DevToolsActivePort");
  const child = spawn(chrome, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
    `--user-data-dir=${profile}`, "--remote-debugging-port=0", "--window-size=1600,1100", "about:blank"
  ], {stdio:"ignore", windowsHide:true});
  let cdp = null;
  try {
    await waitForFile(portFile);
    const port = Number(fs.readFileSync(portFile, "utf8").split(/\r?\n/)[0]);
    assert.ok(Number.isInteger(port) && port > 0, "Chrome DevTools port is invalid");
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const target = targets.find(item => item.type === "page") || targets[0];
    assert.ok(target && target.webSocketDebuggerUrl, "Chrome page target is unavailable");
    cdp = await connectCdp(target.webSocketDebuggerUrl);
    await cdp.call("Page.enable");
    await cdp.call("Runtime.enable");
    await heartbeat(endpoint);
    await cdp.call("Page.navigate", {url:endpoint});
    await sleep(2500);
    const stateResult = await cdp.call("Runtime.evaluate", {
      expression:'JSON.stringify({panel:document.querySelector("#prodPanelState")?.textContent||null,lease:document.querySelector("#prodLeaseState")?.textContent||null,html:document.documentElement.outerHTML})',
      returnByValue:true
    });
    const state = JSON.parse(stateResult.result.value);
    assert.equal(state.panel, "HIDDEN", "Command Deck did not render HIDDEN Browser Companion state");
    assert.equal(state.lease, "PAIRED", "Command Deck did not render PAIRED Browser Companion state");
    fs.writeFileSync(path.join(outputRoot, "command-deck-browser-paired.html"), state.html, "utf8");
    const screenshot = await cdp.call("Page.captureScreenshot", {format:"png", fromSurface:true, captureBeyondViewport:false});
    const screenshotPath = path.join(outputRoot, "command-deck-browser-paired.png");
    fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));
    assert.ok(fs.statSync(screenshotPath).size > 1000, "CDP Command Deck screenshot is unexpectedly small");
    return {screenshot:screenshotPath, screenshotBytes:fs.statSync(screenshotPath).size, renderedPanel:state.panel, renderedLease:state.lease};
  } finally {
    try { if (cdp) cdp.ws.close(); } catch (_) {}
    await closeChrome(child);
    try { fs.rmSync(profile, {recursive:true, force:true, maxRetries:50, retryDelay:100}); } catch (_) {}
  }
}

async function main() {
  assert.equal(process.platform, "win32", "final-browser-bridge-proof.js must run on Windows");
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "jolly-final-browser-bridge-"));
  const runtimeRoot = path.join(tempRoot, "runtime");
  const projectRoot = path.join(tempRoot, "alpha");
  fs.mkdirSync(projectRoot, {recursive:true});
  let runtime = null;
  const report = {schemaVersion:1, candidate:path.basename(sourceRoot), startedAt:new Date().toISOString(), checks:{}};
  try {
    runtime = await launch({open:false, runtimeDir:runtimeRoot});
    assert.equal(runtime.mode, "started");
    const health = await request(runtime.endpoint, "/health");
    assert.equal(health.ok, true);
    await request(runtime.endpoint, "/api/projects", {method:"POST", body:{projectId:"alpha", name:"Alpha", rootPath:projectRoot}});
    const firstLease = await heartbeat(runtime.endpoint);
    report.checks.firstPair = {paired:true, panelVisibility:"HIDDEN"};
    report.checks.rendered = await renderProof(runtime.endpoint);

    runtime.cleanup();
    runtime = null;
    await sleep(900);

    runtime = await launch({open:false, runtimeDir:runtimeRoot});
    assert.equal(runtime.mode, "started");
    const secondLease = await heartbeat(runtime.endpoint, firstLease.nonce);
    report.checks.restartReconnect = {paired:true, freshNonce:secondLease.nonce !== firstLease.nonce, panelVisibility:"HIDDEN"};
    report.ok = true;
  } catch (error) {
    report.ok = false;
    report.error = String(error && error.stack || error);
    throw error;
  } finally {
    try { if (runtime && runtime.cleanup) runtime.cleanup(); } catch (_) {}
    report.finishedAt = new Date().toISOString();
    fs.writeFileSync(path.join(outputRoot, "browser-bridge-proof.json"), JSON.stringify(report, null, 2) + "\n", "utf8");
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    if (report.ok) process.stdout.write("JOLLY_BROWSER_BRIDGE_PROOF_OK\n");
  }
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
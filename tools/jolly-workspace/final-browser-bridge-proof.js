"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawnSync} = require("node:child_process");

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

async function renderProof(endpoint) {
  const chrome = findChrome();
  assert.ok(chrome, "Google Chrome is required for rendered Browser Companion proof");
  await heartbeat(endpoint);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "jolly-browser-proof-chrome-"));
  const screenshot = path.join(outputRoot, "command-deck-browser-paired.png");
  let shot;
  try {
    shot = spawnSync(chrome, [
      "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
      `--user-data-dir=${profile}`, "--window-size=1600,1100", "--virtual-time-budget=3000",
      `--screenshot=${screenshot}`, endpoint
    ], {encoding:"utf8", timeout:30000, windowsHide:true});
  } finally {
    try { fs.rmSync(profile, {recursive:true, force:true, maxRetries:50, retryDelay:100}); } catch (_) {}
  }
  assert.equal(shot.status, 0, `Chrome screenshot failed: ${String(shot.stderr || "").slice(-500)}`);
  assert.ok(fs.existsSync(screenshot) && fs.statSync(screenshot).size > 1000, "paired Command Deck screenshot missing");

  await heartbeat(endpoint);
  const domProfile = fs.mkdtempSync(path.join(os.tmpdir(), "jolly-browser-proof-dom-"));
  let dom;
  try {
    dom = spawnSync(chrome, [
      "--headless=new", "--disable-gpu", "--no-first-run",
      `--user-data-dir=${domProfile}`, "--virtual-time-budget=3000", "--dump-dom", endpoint
    ], {encoding:"utf8", timeout:30000, windowsHide:true, maxBuffer:8 * 1024 * 1024});
  } finally {
    try { fs.rmSync(domProfile, {recursive:true, force:true, maxRetries:50, retryDelay:100}); } catch (_) {}
  }
  assert.equal(dom.status, 0, `Chrome DOM render failed: ${String(dom.stderr || "").slice(-500)}`);
  const html = String(dom.stdout || "");
  assert.match(html, /id="prodPanelState"[^>]*>HIDDEN<\/b>/, "Command Deck did not render HIDDEN Browser Companion state");
  assert.match(html, /id="prodLeaseState"[^>]*>PAIRED<\/b>/, "Command Deck did not render PAIRED Browser Companion state");
  fs.writeFileSync(path.join(outputRoot, "command-deck-browser-paired.html"), html, "utf8");
  return {screenshot, screenshotBytes:fs.statSync(screenshot).size, renderedPanel:"HIDDEN", renderedLease:"PAIRED"};
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
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {listen, createServer} = require("../src/server.js");

async function close(server) {
  await new Promise(resolve => server.close(() => resolve()));
}
async function json(endpoint, pathname, options = {}) {
  const response = await fetch(endpoint + pathname, {
    method: options.method || "GET",
    headers: options.headers || (options.body === undefined ? {} : {"Content-Type":"application/json"}),
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store"
  });
  let body = null;
  try { body = await response.json(); } catch (_) {}
  return {response, body};
}

test("browser bridge acquires a hidden-panel lease and reconnects after server restart", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "jolly-browser-bridge-test-"));
  const stateRoot = path.join(root, "state");
  const runtimeRoot = path.join(root, "runtime");
  fs.mkdirSync(path.join(root, "alpha"), {recursive:true});
  let runtime = await listen({port:0, stateRoot, runtimeRoot});
  let endpoint = `http://127.0.0.1:${runtime.address.port}`;
  try {
    let result = await json(endpoint, "/api/projects", {method:"POST", body:{projectId:"alpha", name:"Alpha", rootPath:path.join(root,"alpha")}});
    assert.equal(result.response.status, 201);
    result = await json(endpoint, "/api/browser-bridge/select-project", {method:"POST", body:{projectId:"alpha"}});
    assert.equal(result.response.status, 200);
    const origin = "chrome-extension://" + "a".repeat(32);
    result = await json(endpoint, "/api/browser-bridge/heartbeat", {method:"POST", headers:{"Content-Type":"application/json","Origin":origin}, body:{conversationPath:"/c/bridge-test", panelVisibility:"HIDDEN"}});
    assert.equal(result.response.status, 200);
    assert.equal(result.body.paired, true);
    assert.equal(result.body.lease.projectId, "alpha");
    assert.equal(result.body.lease.conversationPath, "/c/bridge-test");
    const firstNonce = result.body.lease.nonce;
    result = await json(endpoint, "/api/browser-bridge/status");
    assert.equal(result.body.status.workspaceLeaseActive, true);
    assert.equal(result.body.status.panelVisibility, "HIDDEN");
    const blocked = await json(endpoint, "/api/projects", {method:"POST", headers:{"Content-Type":"application/json","Origin":origin}, body:{projectId:"evil", name:"Evil", rootPath:path.join(root,"evil")}});
    assert.equal(blocked.response.status, 403);
    await close(runtime.server);
    runtime = null;
    runtime = await listen({port:0, stateRoot, runtimeRoot});
    endpoint = `http://127.0.0.1:${runtime.address.port}`;
    await json(endpoint, "/api/browser-bridge/select-project", {method:"POST", body:{projectId:"alpha"}});
    result = await json(endpoint, "/api/browser-bridge/heartbeat", {method:"POST", headers:{"Content-Type":"application/json","Origin":origin}, body:{conversationPath:"/c/bridge-test", panelVisibility:"HIDDEN"}});
    assert.equal(result.body.paired, true);
    assert.notEqual(result.body.lease.nonce, firstNonce);
  } finally {
    if (runtime) await close(runtime.server);
    fs.rmSync(root, {recursive:true, force:true});
  }
});

test("already-finished terminal sessions release their resource lease immediately", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "jolly-terminal-lease-test-"));
  let released = 0;
  const sessions = new Map();
  const terminal = {
    sessions,
    start(projectId, input) {
      const session = {commandId:input.commandId, projectId, status:"COMPLETED", finishedAt:new Date().toISOString()};
      sessions.set(input.commandId, session);
      return session;
    },
    subscribe() { return () => {}; },
    get(id) { return sessions.get(id); },
    cancel() { throw new Error("not used"); }
  };
  const coordination = {
    state:{resourceClaims:{}},
    acquireResource() { return {ok:true, lease:{leaseId:"lease-fast"}}; },
    releaseResource() { released += 1; return {released:true}; },
    conflictRadar() { return []; }
  };
  const lifecycle = {status(){return {supervisor:{heartbeatFresh:true}};}, rollback(){return {};}};
  const runtime = createServer({stateRoot:path.join(root,"state"), runtimeRoot:path.join(root,"runtime"), terminal, coordination, lifecycle});
  await new Promise((resolve,reject)=>{runtime.server.once("error",reject);runtime.server.listen(0,"127.0.0.1",resolve);});
  const endpoint = `http://127.0.0.1:${runtime.server.address().port}`;
  try {
    await json(endpoint, "/api/projects", {method:"POST", body:{projectId:"alpha", name:"Alpha", rootPath:path.join(root,"alpha")}});
    const result = await json(endpoint, "/api/projects/alpha/terminal", {method:"POST", body:{commandId:"fast", actorAgentId:"boss", profile:"workspace", argv:["node","-v"]}});
    assert.equal(result.response.status, 202);
    assert.equal(released, 1);
  } finally {
    await close(runtime.server);
    fs.rmSync(root, {recursive:true, force:true});
  }
});
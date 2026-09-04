"use strict";

const fs = require("node:fs");
const path = require("node:path");

const root = process.argv[2];
if (!root) throw new Error("target repository path is required");

function file(rel) {
  return path.join(root, ...rel.split("/"));
}
function read(rel) {
  return fs.readFileSync(file(rel), "utf8").replace(/\r\n/g, "\n");
}
function write(rel, text) {
  fs.writeFileSync(file(rel), text, "utf8");
}
function replaceRequired(rel, from, to, label) {
  let text = read(rel);
  if (!text.includes(from)) throw new Error(`missing patch target ${label} in ${rel}`);
  text = text.replace(from, to);
  write(rel, text);
}

const server = "workspace/production/src/server.js";
replaceRequired(server,
  'const path = require("node:path");\nconst {WorkspaceStore, safeId, redact}',
  'const path = require("node:path");\nconst crypto = require("node:crypto");\nconst {WorkspaceStore, safeId, redact}',
  "server crypto import");
replaceRequired(server,
  'const DEFAULT_PORT = 8790;\nconst MAX_BODY_BYTES = 256 * 1024;',
  'const DEFAULT_PORT = 8790;\nconst DEFAULT_PORT_RANGE = [8790,8791,8792,8793,8794,8795,8796,8797,8798,8799];\nconst BROWSER_LEASE_MS = 15000;\nconst BROWSER_HEARTBEAT_FRESH_MS = 7000;\nconst MAX_BODY_BYTES = 256 * 1024;',
  "server bridge constants");
replaceRequired(server,
  'function isLoopbackOrigin(origin) {\n  if (!origin) return true;\n  try { const url=new URL(origin); return ["127.0.0.1","localhost","[::1]","::1"].includes(url.hostname); } catch (_) { return false; }\n}\n',
  'function isLoopbackOrigin(origin) {\n  if (!origin) return true;\n  try { const url=new URL(origin); return ["127.0.0.1","localhost","[::1]","::1"].includes(url.hostname); } catch (_) { return false; }\n}\n\nfunction isTrustedExtensionOrigin(origin) {\n  return /^chrome-extension:\\/\\/[a-p]{32}$/.test(String(origin || ""));\n}\n',
  "extension origin guard");
replaceRequired(server,
  '  const startedAt=Date.now();\n  const terminalLeases=new Map();\n',
  '  const startedAt=Date.now();\n  const terminalLeases=new Map();\n  const browserBridge={projectId:null,conversationPath:null,panelVisibility:"UNKNOWN",extensionOrigin:null,lastSeenAt:0,leaseNonce:null,leaseExpiresAt:0};\n\n  function browserBridgeStatus() {\n    const now=Date.now();\n    const heartbeatFresh=browserBridge.lastSeenAt>0 && now-browserBridge.lastSeenAt<=BROWSER_HEARTBEAT_FRESH_MS;\n    const workspaceLeaseActive=heartbeatFresh && browserBridge.leaseExpiresAt>now;\n    return {projectId:browserBridge.projectId,conversationPath:browserBridge.conversationPath,panelVisibility:browserBridge.panelVisibility,heartbeatFresh,workspaceLeaseActive,leaseExpiresAt:workspaceLeaseActive?browserBridge.leaseExpiresAt:null,lastSeenAt:browserBridge.lastSeenAt||null};\n  }\n',
  "bridge runtime state");
replaceRequired(server,
  '      if (!["GET","HEAD","OPTIONS"].includes(method) && !isLoopbackOrigin(req.headers.origin)) return json(res,403,{ok:false,error:"cross-origin mutation rejected"});',
  '      const extensionBridgeMutation=method==="POST" && url.pathname==="/api/browser-bridge/heartbeat" && isTrustedExtensionOrigin(req.headers.origin);\n      if (!["GET","HEAD","OPTIONS"].includes(method) && !isLoopbackOrigin(req.headers.origin) && !extensionBridgeMutation) return json(res,403,{ok:false,error:"cross-origin mutation rejected"});',
  "bridge mutation guard");
replaceRequired(server,
  '      if (method === "GET" && url.pathname === "/api/coordination/conflicts") return json(res,200,{ok:true,conflicts:coordination.conflictRadar(url.searchParams.get("projectId") || null)});\n',
  '      if (method === "GET" && url.pathname === "/api/coordination/conflicts") return json(res,200,{ok:true,conflicts:coordination.conflictRadar(url.searchParams.get("projectId") || null)});\n      if (method === "GET" && url.pathname === "/api/browser-bridge/status") return json(res,200,{ok:true,status:browserBridgeStatus()});\n      if (method === "POST" && url.pathname === "/api/browser-bridge/select-project") {\n        const body=await readJsonBody(req); const projectId=safeId(body.projectId,"projectId"); store.loadProject(projectId);\n        if(browserBridge.projectId!==projectId){browserBridge.projectId=projectId;browserBridge.leaseNonce=null;browserBridge.leaseExpiresAt=0;}\n        return json(res,200,{ok:true,status:browserBridgeStatus()});\n      }\n      if (method === "POST" && url.pathname === "/api/browser-bridge/heartbeat") {\n        const body=await readJsonBody(req); const conversationPath=String(body.conversationPath||"").slice(0,500); const panelVisibility=String(body.panelVisibility||"UNKNOWN").toUpperCase();\n        if(!conversationPath.startsWith("/")) return json(res,400,{ok:false,error:"invalid conversation path"});\n        if(!["VISIBLE","MINIMIZED","HIDDEN"].includes(panelVisibility)) return json(res,400,{ok:false,error:"invalid panel visibility"});\n        browserBridge.conversationPath=conversationPath;browserBridge.panelVisibility=panelVisibility;browserBridge.extensionOrigin=String(req.headers.origin||"");browserBridge.lastSeenAt=Date.now();\n        if(!browserBridge.projectId) return json(res,200,{ok:true,paired:false,status:browserBridgeStatus()});\n        const issuedAt=Date.now();browserBridge.leaseNonce=crypto.randomBytes(16).toString("hex");browserBridge.leaseExpiresAt=issuedAt+BROWSER_LEASE_MS;\n        return json(res,200,{ok:true,paired:true,lease:{projectId:browserBridge.projectId,conversationPath,nonce:browserBridge.leaseNonce,issuedAt,expiresAt:browserBridge.leaseExpiresAt},status:browserBridgeStatus()});\n      }\n',
  "bridge API routes");
replaceRequired(server,
  '            const unsubscribe=terminal.subscribe(commandId,event=>{ if(event.type==="status" && event.status!=="RUNNING"){const info=terminalLeases.get(commandId);if(info){try{coordination.releaseResource(info.projectId,info.agentId,info.leaseId);}catch(_){}terminalLeases.delete(commandId);}unsubscribe();} });',
  '            let unsubscribe=()=>{};\n            const releaseLease=()=>{const info=terminalLeases.get(commandId);if(info){try{coordination.releaseResource(info.projectId,info.agentId,info.leaseId);}catch(_){}terminalLeases.delete(commandId);}};\n            unsubscribe=terminal.subscribe(commandId,event=>{ if(event.type==="status" && event.status!=="RUNNING"){releaseLease();unsubscribe();} });\n            const terminalSnapshot=terminal.get(commandId);if(terminalSnapshot.finishedAt){releaseLease();unsubscribe();}',
  "fast terminal lease release");
replaceRequired(server,
  'function listen(options={}) {\n  const host="127.0.0.1"; const port=Number(options.port!==undefined?options.port:(process.env.JOLLY_WORKSPACE_PORT||DEFAULT_PORT)); const runtime=createServer(options);\n  return new Promise((resolve,reject)=>{runtime.server.once("error",reject);runtime.server.listen(port,host,()=>resolve({...runtime,address:runtime.server.address()}));});\n}',
  'async function listen(options={}) {\n  const host="127.0.0.1";\n  const ports=options.port!==undefined?[Number(options.port)]:(process.env.JOLLY_WORKSPACE_PORT?[Number(process.env.JOLLY_WORKSPACE_PORT)]:DEFAULT_PORT_RANGE);\n  let lastError=null;\n  for(const port of ports){\n    const runtime=createServer(options);\n    try{return await new Promise((resolve,reject)=>{const onError=error=>reject(error);runtime.server.once("error",onError);runtime.server.listen(port,host,()=>{runtime.server.off("error",onError);resolve({...runtime,address:runtime.server.address()});});});}\n    catch(error){lastError=error;try{runtime.server.close();}catch(_){}if(!(error&&error.code==="EADDRINUSE"))throw error;}\n  }\n  throw lastError||new Error(`No free Jolly Workspace port starting at ${DEFAULT_PORT}`);\n}',
  "bounded loopback port range");
replaceRequired(server,
  'module.exports={createServer,listen,readJsonBody,isLoopbackOrigin};',
  'module.exports={createServer,listen,readJsonBody,isLoopbackOrigin,isTrustedExtensionOrigin};',
  "server exports");

replaceRequired("workspace/production/src/launcher.js",
  'env:{...process.env,JOLLY_WORKSPACE_PORT:"0",JOLLY_WORKSPACE_STATE:stateRoot,JOLLY_WORKSPACE_HOME:runtimeDir,JOLLY_WORKSPACE_SUPERVISOR_NONCE:supervisor.instanceNonce}',
  'env:{...process.env,JOLLY_WORKSPACE_PORT:"",JOLLY_WORKSPACE_STATE:stateRoot,JOLLY_WORKSPACE_HOME:runtimeDir,JOLLY_WORKSPACE_SUPERVISOR_NONCE:supervisor.instanceNonce}',
  "launcher bounded discovery ports");

const manifestPath = "companion/browser/manifest.json";
const manifest = JSON.parse(read(manifestPath));
if (!manifest.host_permissions.includes("http://127.0.0.1/*")) manifest.host_permissions.push("http://127.0.0.1/*");
write(manifestPath, JSON.stringify(manifest, null, 2) + "\n");

const background = "companion/browser/background.js";
replaceRequired(background,
  'const MAX_RESUME_IDS = 250;\n',
  'const MAX_RESUME_IDS = 250;\nconst BRIDGE_PORTS = [8790,8791,8792,8793,8794,8795,8796,8797,8798,8799];\nconst BRIDGE_TIMEOUT_MS = 300;\nlet lastBridgeEndpoint = null;\n',
  "background bridge constants");
replaceRequired(background,
  'chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {\n  if (!message || message.type !== "jolly-resume-reservation") return false;\n  const run = () => reserveResume(message, sender);\n  const next = reservationQueue.then(run, run);\n  reservationQueue = next.catch(() => {});\n  next.then(sendResponse, error => sendResponse({ok:false, granted:false, reason:String(error && error.message || error)}));\n  return true;\n});',
  'async function fetchBridgeJson(url, options = {}) {\n  const controller = new AbortController();\n  const timeout = setTimeout(() => controller.abort(), BRIDGE_TIMEOUT_MS);\n  try {\n    const response = await fetch(url, {...options, signal:controller.signal, cache:"no-store"});\n    if (!response.ok) return null;\n    return await response.json();\n  } catch (_) {\n    return null;\n  } finally {\n    clearTimeout(timeout);\n  }\n}\n\nasync function forwardBridgeHeartbeat(message, sender) {\n  if (!sender || !sender.tab || !sender.tab.id) return {ok:false, reason:"missing_tab"};\n  const payload = {conversationPath:String(message.conversationPath || "").slice(0,500), panelVisibility:String(message.panelVisibility || "VISIBLE").toUpperCase()};\n  const bases = [];\n  if (lastBridgeEndpoint) bases.push(lastBridgeEndpoint);\n  for (const port of BRIDGE_PORTS) { const base=`http://127.0.0.1:${port}`; if (!bases.includes(base)) bases.push(base); }\n  for (const base of bases) {\n    const health = await fetchBridgeJson(base + "/health");\n    if (!health || health.ok !== true || health.service !== "jolly-workspace-kernel") continue;\n    const result = await fetchBridgeJson(base + "/api/browser-bridge/heartbeat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});\n    if (!result || result.ok !== true) continue;\n    lastBridgeEndpoint = base;\n    if (result.paired && result.lease) {\n      try { await chrome.tabs.sendMessage(sender.tab.id, {type:"jolly-production-bridge", command:"workspace-lease", lease:result.lease}); } catch (_) {}\n    }\n    return {ok:true, paired:Boolean(result.paired), endpoint:base};\n  }\n  lastBridgeEndpoint = null;\n  return {ok:false, reason:"workspace_not_found"};\n}\n\nchrome.runtime.onMessage.addListener((message, sender, sendResponse) => {\n  if (!message) return false;\n  if (message.type === "jolly-browser-heartbeat") {\n    forwardBridgeHeartbeat(message, sender).then(sendResponse, error => sendResponse({ok:false, reason:String(error && error.message || error)}));\n    return true;\n  }\n  if (message.type !== "jolly-resume-reservation") return false;\n  const run = () => reserveResume(message, sender);\n  const next = reservationQueue.then(run, run);\n  reservationQueue = next.catch(() => {});\n  next.then(sendResponse, error => sendResponse({ok:false, granted:false, reason:String(error && error.message || error)}));\n  return true;\n});',
  "background bridge heartbeat transport");

const bridge = "companion/browser/production-bridge.js";
replaceRequired(bridge,
  '  const LEASE_CHECK_MS = 2000;\n  const MAX_LEASE_MS = 30000;',
  '  const LEASE_CHECK_MS = 2000;\n  const BRIDGE_HEARTBEAT_MS = 2000;\n  const MAX_LEASE_MS = 30000;',
  "content heartbeat constant");
replaceRequired(bridge,
  '  chrome.storage.onChanged.addListener((changes, area) => {',
  '  async function sendBridgeHeartbeat() {\n    if (document.hidden) return;\n    try {\n      await chrome.runtime.sendMessage({type:"jolly-browser-heartbeat", conversationPath:location.pathname, panelVisibility:panelVisibility(settings.panelVisibility)});\n    } catch (_) {}\n  }\n\n  chrome.storage.onChanged.addListener((changes, area) => {',
  "content heartbeat function");
replaceRequired(bridge,
  '    settings = changes[SETTINGS_KEY].newValue || {};\n    scheduleVisibility();',
  '    settings = changes[SETTINGS_KEY].newValue || {};\n    scheduleVisibility();\n    sendBridgeHeartbeat();',
  "heartbeat on state change");
replaceRequired(bridge,
  '    scheduleVisibility();\n    return setCompatibilityWorkspaceAttached(Boolean(lease));',
  '    scheduleVisibility();\n    sendBridgeHeartbeat();\n    return setCompatibilityWorkspaceAttached(Boolean(lease));',
  "initial heartbeat");
replaceRequired(bridge,
  '  setInterval(expireLeaseIfNeeded, LEASE_CHECK_MS);',
  '  document.addEventListener("visibilitychange", () => { if (!document.hidden) sendBridgeHeartbeat(); });\n  setInterval(expireLeaseIfNeeded, LEASE_CHECK_MS);\n  setInterval(sendBridgeHeartbeat, BRIDGE_HEARTBEAT_MS);',
  "heartbeat interval");

const production = "workspace/production/web/production.js";
replaceRequired(production,
  '  const prod = {projectId:null, projects:[], project:null, inbox:[], conflicts:[], lifecycle:null, timer:null, busy:false};',
  '  const prod = {projectId:null, projects:[], project:null, inbox:[], conflicts:[], lifecycle:null, bridge:null, timer:null, busy:false};',
  "production bridge state");
replaceRequired(production,
  '  function renderTabBadges(){',
  '  function renderBridge(){const state=prod.bridge;const panel=$("#prodPanelState");const lease=$("#prodLeaseState");if(!panel||!lease)return;panel.textContent=state&&state.panelVisibility||"UNKNOWN";lease.textContent=state&&state.workspaceLeaseActive?"PAIRED":"WAITING";lease.classList.toggle("good",Boolean(state&&state.workspaceLeaseActive));}\n\n  function renderTabBadges(){',
  "production bridge renderer");
replaceRequired(production,
  '      if(active!==prod.projectId)prod.projectId=active;renderTargets();\n      const lifecycleResult=await api("/api/production/status");prod.lifecycle=lifecycleResult.status;renderLifecycle();',
  '      if(active!==prod.projectId)prod.projectId=active;renderTargets();\n      if(prod.projectId)await api("/api/browser-bridge/select-project",{method:"POST",body:{projectId:prod.projectId}});\n      const [lifecycleResult,bridgeResult]=await Promise.all([api("/api/production/status"),api("/api/browser-bridge/status")]);prod.lifecycle=lifecycleResult.status;prod.bridge=bridgeResult.status;renderLifecycle();renderBridge();',
  "production bridge refresh");

console.log("JOLLY_PLUGIN_PATCH_OK");
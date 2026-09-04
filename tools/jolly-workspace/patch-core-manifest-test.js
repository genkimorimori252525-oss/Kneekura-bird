"use strict";

const fs = require("node:fs");
const path = require("node:path");

const root = process.argv[2];
if (!root) throw new Error("target repository path is required");

const target = path.join(root, "tests", "core.test.js");
let text = fs.readFileSync(target, "utf8").replace(/\r\n/g, "\n");
const before = 'assert.deepEqual(manifest.host_permissions, ["https://chatgpt.com/*"]);';
const after = 'assert.deepEqual(manifest.host_permissions, ["https://chatgpt.com/*", "http://127.0.0.1/*"]);';

if (!text.includes(before)) {
  throw new Error("manifest host permission assertion target missing");
}
text = text.replace(before, after);
fs.writeFileSync(target, text, "utf8");
console.log("JOLLY_CORE_MANIFEST_TEST_PATCH_OK");
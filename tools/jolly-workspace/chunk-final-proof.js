"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const root = process.cwd();
const source = path.join(root, "tools", "jolly-workspace", "final-evidence", "command-deck-browser-paired.png");
const out = path.join(root, "tools", "jolly-workspace", "final-evidence", "png-base64");
const data = fs.readFileSync(source);
const b64 = data.toString("base64");
fs.rmSync(out, {recursive:true, force:true});
fs.mkdirSync(out, {recursive:true});
const chunkSize = 80000;
let count = 0;
for (let i = 0; i < b64.length; i += chunkSize) {
  fs.writeFileSync(path.join(out, `chunk-${String(count).padStart(2,"0")}.txt`), b64.slice(i, i + chunkSize), "ascii");
  count += 1;
}
fs.writeFileSync(path.join(out, "meta.json"), JSON.stringify({bytes:data.length, sha256:crypto.createHash("sha256").update(data).digest("hex"), base64Chars:b64.length, chunkSize, count}, null, 2) + "\n", "utf8");
console.log(`JOLLY_FINAL_PROOF_CHUNKED count=${count} bytes=${data.length}`);
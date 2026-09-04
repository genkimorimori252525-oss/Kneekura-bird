"use strict";

const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const originalSpawnSync = childProcess.spawnSync;
childProcess.spawnSync = function patchedSpawnSync(command, args, options) {
  if (Array.isArray(args)) {
    const index = args.findIndex(arg => String(arg).startsWith("--screenshot="));
    if (index >= 0) {
      const value = String(args[index]).slice("--screenshot=".length);
      if (path.isAbsolute(value)) {
        const directory = path.dirname(value);
        fs.mkdirSync(directory, {recursive:true});
        const nextArgs = args.slice();
        nextArgs[index] = `--screenshot=${path.basename(value)}`;
        return originalSpawnSync.call(childProcess, command, nextArgs, {...(options || {}), cwd:directory});
      }
    }
  }
  return originalSpawnSync.call(childProcess, command, args, options);
};
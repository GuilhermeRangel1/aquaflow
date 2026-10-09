import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const event = JSON.parse(fs.readFileSync(0, "utf8"));
const rootResult = spawnSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" });
if (rootResult.status !== 0) process.exit(0);
const root = rootResult.stdout.trim();
const input = event.tool_input ?? {};
const candidatePaths = new Set();

function visit(value, key = "") {
  if (typeof value === "string") {
    if (/^(file_path|path|filename)$/i.test(key)) candidatePaths.add(value);
    if (key === "command") {
      for (const match of value.matchAll(/(?:\*\*\* (?:Update|Add|Delete) File: |\+\+\+ b\/)([^\r\n]+)/g)) {
        candidatePaths.add(match[1].trim());
      }
    }
  } else if (Array.isArray(value)) {
    value.forEach((item) => visit(item, key));
  } else if (value && typeof value === "object") {
    for (const [childKey, childValue] of Object.entries(value)) visit(childValue, childKey);
  }
}

visit(input);
const frontendRoot = path.join(root, "frontend");
const extensions = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".css"]);
const targets = [];

for (const candidate of candidatePaths) {
  const normalizedCandidate = candidate.replaceAll("\\", "/");
  const absolute = path.isAbsolute(candidate)
    ? candidate
    : normalizedCandidate.startsWith("frontend/")
      ? path.resolve(root, candidate)
      : path.resolve(event.cwd ?? root, candidate);
  const relative = path.relative(frontendRoot, absolute);
  if (relative.startsWith("..") || path.isAbsolute(relative) || !extensions.has(path.extname(absolute))) continue;
  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) continue;
  targets.push(absolute);
}

if (targets.length === 0) process.exit(0);

const result = spawnSync("npm", ["exec", "--", "prettier", "--write", ...targets], {
  cwd: frontendRoot,
  encoding: "utf8",
  shell: process.platform === "win32",
});

if (result.status !== 0) {
  process.stdout.write(JSON.stringify({
    systemMessage: "Não consegui formatar automaticamente o arquivo do frontend. Confira a instalação do Prettier em frontend/.",
  }));
}

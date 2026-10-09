import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const event = JSON.parse(fs.readFileSync(0, "utf8"));
const rootResult = spawnSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" });
if (rootResult.status !== 0) process.exit(0);
const root = rootResult.stdout.trim();
const changed = spawnSync("git", ["status", "--porcelain", "--untracked-files=all"], {
  cwd: root,
  encoding: "utf8",
});
if (changed.status !== 0 || !changed.stdout.trim()) process.exit(0);

const checks = [];
const changedPaths = changed.stdout.split(/\r?\n/).filter(Boolean).map((line) => line.slice(3).replaceAll("\\", "/"));
const frontendPaths = changedPaths.map((item) => item.includes(" -> ") ? item.split(" -> ").at(-1) : item)
  .filter((item) => item.startsWith("frontend/"));
const frontendChanged = frontendPaths.length > 0;
const backendChanged = changedPaths.some((item) => (item.includes(" -> ") ? item.split(" -> ").at(-1) : item).startsWith("backend/"));

function run(label, command, args, cwd, windowsShell = false) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    shell: windowsShell && process.platform === "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });
  checks.push({ label, passed: result.status === 0 });
}

if (frontendChanged) {
  const formatTargets = frontendPaths
    .map((item) => item.replace(/^frontend\//, ""))
    .filter((item) => /\.(?:ts|tsx|js|jsx|mjs|css)$/.test(item));
  if (formatTargets.length > 0) {
    run("formatação do frontend", "npm", ["exec", "--", "prettier", "--check", ...formatTargets], path.join(root, "frontend"), true);
  }
  run("lint do frontend", "npm", ["run", "lint"], path.join(root, "frontend"), true);
  run("tipos do frontend", "npm", ["run", "typecheck"], path.join(root, "frontend"), true);
  run("testes do frontend", "npm", ["test"], path.join(root, "frontend"), true);
}

if (backendChanged) {
  const venvPython = path.join(root, "backend", ".venv", "Scripts", "python.exe");
  const python = fs.existsSync(venvPython) ? venvPython : (process.platform === "win32" ? "py" : "python3");
  const prefix = python === "py" ? ["-3"] : [];
  run("testes da API", python, [...prefix, "-m", "pytest", "-q"], path.join(root, "backend"), true);
  run("lint da API", python, [...prefix, "-m", "ruff", "check", "app", "tests", "migrations"], path.join(root, "backend"), true);
  run("tipos da API", python, [...prefix, "-m", "mypy", "app"], path.join(root, "backend"), true);
}

const failures = checks.filter((check) => !check.passed).map((check) => check.label);
if (failures.length === 0) {
  process.stdout.write(JSON.stringify({ systemMessage: "Quality gate aprovado para os arquivos alterados." }));
} else if (!event.stop_hook_active) {
  process.stdout.write(JSON.stringify({
    decision: "block",
    reason: `O quality gate encontrou falhas em: ${failures.join(", ")}. Corrija os problemas e rode as verificações novamente.`,
  }));
} else {
  process.stdout.write(JSON.stringify({
    systemMessage: `O quality gate ainda falhou em: ${failures.join(", ")}. A rodada será encerrada para evitar repetição automática; revise essas verificações antes do commit.`,
  }));
}

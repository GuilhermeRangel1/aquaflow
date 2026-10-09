import fs from "node:fs";

const event = JSON.parse(fs.readFileSync(0, "utf8"));
const input = event.tool_input ?? {};
const strings = [];
const paths = [];

function visit(value, key = "") {
  if (typeof value === "string") {
    strings.push(value);
    if (/^(file_path|path|filename)$/i.test(key)) paths.push(value);
    if (key === "command") {
      for (const match of value.matchAll(/(?:\*\*\* (?:Update|Add|Delete) File: |\+\+\+ b\/)([^\r\n]+)/g)) {
        paths.push(match[1].trim());
      }
    }
  } else if (Array.isArray(value)) {
    value.forEach((item) => visit(item, key));
  } else if (value && typeof value === "object") {
    for (const [childKey, childValue] of Object.entries(value)) visit(childValue, childKey);
  }
}

visit(input);

const shellCommand = typeof input.command === "string" ? input.command : "";
if (/(?:^|[\s"'`])(?:\.\/)?\.env(?:\.[A-Za-z0-9_-]+)?(?=$|[\s"'`])/i.test(shellCommand)
  && !/\.env\.(?:example|sample|template)\b/i.test(shellCommand)) {
  paths.push(".env");
}

const sensitivePath = paths.find((value) => {
  const normalized = value.replaceAll("\\", "/");
  const name = normalized.split("/").at(-1) ?? "";
  return /^\.env(?:\.|$)/i.test(name) && !/^\.env\.(?:example|sample|template)$/i.test(name)
    || /\.(?:pem|p12|pfx|key)$/i.test(name)
    || /(?:^|\/)(?:id_rsa|id_ed25519|credentials\.json)$/i.test(normalized);
});

const secretPatterns = [
  ["chave privada", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ["chave AWS", /\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/],
  ["token GitHub", /\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/],
  ["token Slack", /\bxox[baprs]-[A-Za-z0-9-]{20,}\b/],
  ["chave Google", /\bAIza[0-9A-Za-z_-]{35}\b/],
  ["chave de API", /\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b/],
];

// Patterns below target credential-like assignments while allowing documented local placeholders.
const assignmentPattern = /\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|database[_-]?url|jwt[_-]?secret|password|passwd|secret|device[_-]?key|token)\b\s*[:=]\s*["'`]([^"'`\s]{16,})["'`]/i;
const placeholders = /(?:example|placeholder|changeme|change[-_ ]this|your[-_ ]|test[-_ ]only|development[-_ ]only|local[-_ ]only|dummy|redacted|<[^>]+>|\$\{)/i;
let detected = sensitivePath ? "arquivo sensível" : "";

if (!detected) {
  for (const text of strings) {
    const found = secretPatterns.find(([, pattern]) => pattern.test(text));
    if (found) {
      detected = found[0];
      break;
    }
    const assignment = text.match(assignmentPattern);
    if (assignment && !placeholders.test(assignment[1])) {
      detected = "credencial literal em uma atribuição";
      break;
    }
  }
}

if (detected) {
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: `A edição foi bloqueada: foi detectado ${detected}. Mantenha credenciais em variáveis de ambiente e use apenas .env.example para exemplos.`,
    },
  }));
}

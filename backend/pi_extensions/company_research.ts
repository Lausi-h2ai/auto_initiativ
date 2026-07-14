import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { spawn } from "node:child_process";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { basename, delimiter, relative, resolve } from "node:path";

const MAX_COMMAND_TIMEOUT_MS = 120000;
const MAX_COMMAND_OUTPUT_BYTES = 128000;
const WRITE_DIRECTORIES = {
  company: "companies",
  contact: "contacts",
  fit: "fit_evaluations",
  job: "jobs",
  jobFit: "job_fit_evaluations",
} as const;

function workspacePath(...parts: string[]): string {
  return resolve(process.cwd(), ...parts);
}

function runRoot(): string {
  return workspacePath("..");
}

function assertWithin(root: string, path: string): void {
  const rel = relative(root, path);
  if (rel.startsWith("..") || rel === "..") {
    throw new Error("Path escapes company research workspace boundary");
  }
}

function assertChildPath(root: string, path: string): void {
  const rel = relative(root, path);
  if (rel.startsWith("..") || rel === ".." || resolve(path) === resolve(root)) {
    throw new Error("Path escapes company research workspace boundary");
  }
}

function safeName(filename: string): string {
  const clean = basename(filename);
  if (!clean || clean === "." || clean === ".." || clean !== filename || !clean.endsWith(".json")) {
    throw new Error("Invalid JSON filename");
  }
  return clean;
}

function safeEnv(): NodeJS.ProcessEnv {
  const allowed = new Set([
    "APPDATA",
    "COMSPEC",
    "HOME",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "PLAYWRIGHT_BROWSERS_PATH",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
  ]);
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (allowed.has(key.toUpperCase()) && value !== undefined) {
      env[key] = value;
    }
  }
  const repoRoot = process.env.COMPANY_RESEARCH_REPO_ROOT;
  if (repoRoot) {
    env.COMPANY_RESEARCH_REPO_ROOT = repoRoot;
    env.PYTHONPATH = repoRoot + (process.env.PYTHONPATH ? `${delimiter}${process.env.PYTHONPATH}` : "");
  }
  env.PI_TELEMETRY = "0";
  return env;
}

async function listJsonFiles(root: string): Promise<string[]> {
  try {
    const entries = await readdir(root, { withFileTypes: true });
    return entries
      .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
      .map((entry) => entry.name)
      .sort();
  } catch {
    return [];
  }
}

function truncateOutput(value: string, limit: number): { text: string; truncated: boolean } {
  const bytes = Buffer.byteLength(value, "utf8");
  if (bytes <= limit) {
    return { text: value, truncated: false };
  }
  return {
    text: Buffer.from(value, "utf8").subarray(0, limit).toString("utf8"),
    truncated: true,
  };
}

function runShell(command: string, cwd: string, timeoutMs: number): Promise<Record<string, unknown>> {
  return new Promise((resolvePromise, reject) => {
    let stdout = "";
    let stderr = "";
    let killedByTimeout = false;
    const child = spawn(command, {
      cwd,
      env: safeEnv(),
      shell: true,
      windowsHide: true,
    });
    const timer = setTimeout(() => {
      killedByTimeout = true;
      child.kill();
    }, timeoutMs);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
      if (Buffer.byteLength(stdout, "utf8") > MAX_COMMAND_OUTPUT_BYTES * 2) {
        child.kill();
      }
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
      if (Buffer.byteLength(stderr, "utf8") > MAX_COMMAND_OUTPUT_BYTES * 2) {
        child.kill();
      }
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const cappedStdout = truncateOutput(stdout, MAX_COMMAND_OUTPUT_BYTES);
      const cappedStderr = truncateOutput(stderr, MAX_COMMAND_OUTPUT_BYTES);
      resolvePromise({
        code,
        timed_out: killedByTimeout,
        stdout: cappedStdout.text,
        stderr: cappedStderr.text,
        truncated: cappedStdout.truncated || cappedStderr.truncated,
      });
    });
  });
}

async function writeArtifact(kind: keyof typeof WRITE_DIRECTORIES, filename: string, json: string): Promise<Record<string, unknown>> {
  const parsed = JSON.parse(json);
  const cleanName = safeName(filename);
  const outputRoot = workspacePath("../output", WRITE_DIRECTORIES[kind]);
  const outputPath = resolve(outputRoot, cleanName);
  assertChildPath(outputRoot, outputPath);
  await mkdir(outputRoot, { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
  return { filename: cleanName, path: `../output/${WRITE_DIRECTORIES[kind]}/${cleanName}` };
}

export default function companyResearch(pi: ExtensionAPI) {
  pi.registerTool({
    name: "company_research_list_inputs",
    label: "List Research Inputs",
    description: "List approved research input files from ../input.",
    parameters: Type.Object({}),
    async execute() {
      const inputRoot = workspacePath("../input");
      const files = await listJsonFiles(inputRoot);
      const schemaFiles = await listJsonFiles(resolve(inputRoot, "schemas"));
      const details = { files, schemas: schemaFiles };
      return { content: [{ type: "text", text: JSON.stringify(details) }], details };
    },
  });

  pi.registerTool({
    name: "company_research_read_input",
    label: "Read Research Input",
    description: "Read an approved UTF-8 JSON input file from ../input or ../input/schemas by exact relative path.",
    parameters: Type.Object({
      path: Type.String({ description: "Relative input path such as campaign.json or schemas/company_candidate.schema.json." }),
    }),
    async execute(_toolCallId, params) {
      const inputRoot = workspacePath("../input");
      const inputPath = resolve(inputRoot, params.path);
      assertChildPath(inputRoot, inputPath);
      const content = await readFile(inputPath, "utf8");
      return { content: [{ type: "text", text: content }], details: { path: params.path } };
    },
  });

  pi.registerTool({
    name: "company_research_shell",
    label: "Run Research Shell Command",
    description:
      "Run a shell command inside the prepared run workspace with a sanitized environment, timeout, and capped stdout/stderr. Use for Playwright-backed public web research and local file inspection only.",
    parameters: Type.Object({
      command: Type.String({ description: "Shell command to run." }),
      cwd: Type.Optional(Type.String({ description: "Optional run-root-relative working directory. Defaults to workspace." })),
      timeout_ms: Type.Optional(Type.Number({ description: "Timeout in milliseconds, capped at 120000." })),
    }),
    async execute(_toolCallId, params) {
      const root = runRoot();
      const cwd = resolve(root, params.cwd || "workspace");
      assertWithin(root, cwd);
      const timeoutMs = Math.max(1000, Math.min(Number(params.timeout_ms || 30000), MAX_COMMAND_TIMEOUT_MS));
      const result = await runShell(params.command, cwd, timeoutMs);
      return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
    },
  });

  pi.registerTool({
    name: "company_research_write_company",
    label: "Write Company Candidate",
    description: "Write one schema-validatable company candidate JSON artifact under ../output/companies.",
    parameters: Type.Object({
      filename: Type.String({ description: "A stable JSON filename such as acme-corp.json." }),
      json: Type.String({ description: "Complete company_candidate JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const details = await writeArtifact("company", params.filename, params.json);
      return { content: [{ type: "text", text: `Wrote ${details.path}` }], details };
    },
  });

  pi.registerTool({
    name: "company_research_write_contact",
    label: "Write Contact Candidate",
    description: "Write one schema-validatable public career contact candidate JSON artifact under ../output/contacts.",
    parameters: Type.Object({
      filename: Type.String({ description: "A stable JSON filename such as acme-corp-careers.json." }),
      json: Type.String({ description: "Complete contact_candidate JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const details = await writeArtifact("contact", params.filename, params.json);
      return { content: [{ type: "text", text: `Wrote ${details.path}` }], details };
    },
  });

  pi.registerTool({
    name: "company_research_write_fit_evaluation",
    label: "Write Fit Evaluation",
    description: "Write one schema-validatable fit evaluation JSON artifact under ../output/fit_evaluations.",
    parameters: Type.Object({
      filename: Type.String({ description: "A stable JSON filename such as acme-corp-fit.json." }),
      json: Type.String({ description: "Complete fit_evaluation JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const details = await writeArtifact("fit", params.filename, params.json);
      return { content: [{ type: "text", text: `Wrote ${details.path}` }], details };
    },
  });

  pi.registerTool({
    name: "job_research_write_job",
    label: "Write Job Candidate",
    description: "Write one schema-validatable job posting candidate under ../output/jobs.",
    parameters: Type.Object({
      filename: Type.String({ description: "A stable JSON filename." }),
      json: Type.String({ description: "Complete job_posting_candidate JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const details = await writeArtifact("job", params.filename, params.json);
      return { content: [{ type: "text", text: `Wrote ${details.path}` }], details };
    },
  });

  pi.registerTool({
    name: "job_research_write_fit_evaluation",
    label: "Write Job Fit Evaluation",
    description: "Write one schema-validatable vacancy fit evaluation under ../output/job_fit_evaluations.",
    parameters: Type.Object({
      filename: Type.String({ description: "A stable JSON filename." }),
      json: Type.String({ description: "Complete job_fit_evaluation JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const details = await writeArtifact("jobFit", params.filename, params.json);
      return { content: [{ type: "text", text: `Wrote ${details.path}` }], details };
    },
  });
}

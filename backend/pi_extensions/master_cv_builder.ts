import { Type } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { relative, resolve } from "node:path";

function workspacePath(...parts: string[]): string {
  return resolve(process.cwd(), ...parts);
}

function assertChildPath(root: string, path: string): void {
  const rel = relative(root, path);
  if (rel.startsWith("..") || rel === ".." || resolve(path) === resolve(root)) {
    throw new Error("Path escapes master CV workspace boundary");
  }
}

export default function masterCvBuilder(pi: ExtensionAPI) {
  pi.registerTool({
    name: "master_cv_list_sources",
    label: "List Approved CV Sources",
    description: "List the source documents made available to this builder session.",
    parameters: Type.Object({}),
    async execute() {
      const inputRoot = workspacePath("../input");
      const names = (await readdir(inputRoot)).filter((name) => !name.endsWith(".extracted.json"));
      return { content: [{ type: "text", text: JSON.stringify(names.sort()) }], details: {} };
    },
  });

  pi.registerTool({
    name: "master_cv_read_source_text",
    label: "Read Extracted CV Source",
    description: "Read backend-extracted text for one listed source document. Never returns raw file or image bytes.",
    parameters: Type.Object({ filename: Type.String() }),
    async execute(_toolCallId, params) {
      if (!params.filename || params.filename.includes("/") || params.filename.includes("\\") || params.filename === "." || params.filename === "..") {
        throw new Error("Invalid source filename");
      }
      const inputRoot = workspacePath("../input");
      const extractedPath = resolve(inputRoot, `${params.filename}.extracted.json`);
      assertChildPath(inputRoot, extractedPath);
      const payload = await readFile(extractedPath, "utf8");
      return { content: [{ type: "text", text: payload.slice(0, 140000) }], details: {} };
    },
  });

  pi.registerTool({
    name: "master_cv_write_candidate",
    label: "Write Master CV Candidate",
    description: "Write the complete structured candidate document to ../output/master_cv_document.json. HTML, CSS, paths, URLs, and image bytes are not accepted.",
    parameters: Type.Object({
      json: Type.String({ description: "Complete candidate JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const parsed = JSON.parse(params.json);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Candidate must be a JSON object");
      }
      const forbidden = JSON.stringify(parsed).match(/(?:<\/?(?:html|style|script)|file:\/\/|https?:\/\/|data:image)/i);
      if (forbidden) {
        throw new Error("Candidate contains forbidden presentation or asset content");
      }
      const outputRoot = workspacePath("../output");
      const outputPath = resolve(outputRoot, "master_cv_document.json");
      assertChildPath(outputRoot, outputPath);
      await mkdir(outputRoot, { recursive: true });
      await writeFile(outputPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
      return { content: [{ type: "text", text: "Wrote structured master CV candidate" }], details: {} };
    },
  });

  pi.registerTool({
    name: "master_cv_write_claim_proposals",
    label: "Write Master CV Claim Proposals",
    description: "Write unsupported factual proposals to ../output/master_cv_claim_proposals.json for explicit user review.",
    parameters: Type.Object({
      json: Type.String({ description: "Complete claim-proposals JSON document as a string." }),
    }),
    async execute(_toolCallId, params) {
      const parsed = JSON.parse(params.json);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Claim proposals must be a JSON object");
      }
      const forbidden = JSON.stringify(parsed).match(/(?:<\/?(?:html|style|script)|file:\/\/|https?:\/\/|data:image)/i);
      if (forbidden) {
        throw new Error("Claim proposals contain forbidden presentation or asset content");
      }
      const outputRoot = workspacePath("../output");
      const outputPath = resolve(outputRoot, "master_cv_claim_proposals.json");
      assertChildPath(outputRoot, outputPath);
      await mkdir(outputRoot, { recursive: true });
      await writeFile(outputPath, `${JSON.stringify(parsed, null, 2)}\n`, "utf8");
      return { content: [{ type: "text", text: "Wrote structured claim proposals for review" }], details: {} };
    },
  });

  pi.registerTool({
    name: "master_cv_write_latest_reply",
    label: "Write Latest Master CV Reply",
    description: "Write the exact clean user-visible assistant reply to ../logs/latest_assistant_message.txt.",
    parameters: Type.Object({ text: Type.String() }),
    async execute(_toolCallId, params) {
      const logsRoot = workspacePath("../logs");
      const replyPath = resolve(logsRoot, "latest_assistant_message.txt");
      assertChildPath(logsRoot, replyPath);
      await mkdir(logsRoot, { recursive: true });
      await writeFile(replyPath, params.text.trim(), "utf8");
      return { content: [{ type: "text", text: "Wrote latest reply" }], details: {} };
    },
  });
}

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(process.cwd(), "..");
const windows = process.platform === "win32";
const candidates = [
  process.env.PYTHON,
  resolve(root, windows ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
  resolve(root, "backend", windows ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
  windows ? "python" : "python3",
].filter(Boolean);
const python = candidates.find((candidate) => candidate.includes("/") || candidate.includes("\\") ? existsSync(candidate) : true);
const result = spawnSync(python, [resolve(root, "backend/scripts/export_openapi_types.py")], { cwd: process.cwd(), stdio: "inherit" });
process.exit(result.status ?? 1);

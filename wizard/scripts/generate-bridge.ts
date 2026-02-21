/**
 * Bridge script: reads WizardState overrides from stdin,
 * merges with DEFAULT_WIZARD_STATE, calls generateProject(),
 * and writes GeneratedFile[] JSON to stdout.
 *
 * Usage:
 *   echo '{"storage": "disk"}' | pnpm tsx scripts/generate-bridge.ts
 */

import { generateProject } from "../src/lib/generator/generateProject.js";
import { DEFAULT_WIZARD_STATE } from "../src/types/wizard.js";
import type { WizardState } from "../src/types/wizard.js";

function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    process.stdin.on("data", (chunk) => chunks.push(chunk));
    process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    process.stdin.on("error", reject);
  });
}

async function main() {
  const input = await readStdin();
  const overrides = JSON.parse(input || "{}");

  // Deep merge: top-level spread + nested objects
  const state: WizardState = {
    ...DEFAULT_WIZARD_STATE,
    ...overrides,
    storageConfig: {
      ...DEFAULT_WIZARD_STATE.storageConfig,
      ...(overrides.storageConfig || {}),
    },
  };

  // If models are provided, use them as-is (don't merge with default)
  if (overrides.models) {
    state.models = overrides.models;
  }

  const files = generateProject(state);
  process.stdout.write(JSON.stringify(files));
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});

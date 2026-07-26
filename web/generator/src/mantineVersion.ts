/**
 * Mantine Version Configuration
 *
 * Handles version-specific dependency management and source file patching
 * for Mantine 7 and 8 support.
 */

import * as fs from 'fs/promises';
import * as path from 'path';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type MantineVersion = '7' | '8';

export interface VersionDeps {
  dependencies: Record<string, string>;
  devDependencies: Record<string, string>;
  /** Keys to remove from dependencies */
  removeDeps: string[];
  /** Keys to remove from devDependencies */
  removeDevDeps: string[];
  /** pnpm overrides to suppress peer-dep conflicts */
  pnpmOverrides?: Record<string, string>;
}

/**
 * `.specstarrc.json` — the project's hand-edited generator config.
 *
 * Every field is optional on read: the file is written by `init`/`integrate`
 * but developers edit it afterwards, so treat anything missing as unset.
 */
export interface SpecStarRc {
  mantineVersion: MantineVersion;
  /** Display name for the admin console. Defaults to the OpenAPI `info.title`. */
  title: string;
  /** Path to the logo asset, served from the app's `public/` directory. */
  logo: string;
}

// ---------------------------------------------------------------------------
// Version-specific dependency maps
// ---------------------------------------------------------------------------

/**
 * Mantine 8 dependency overrides.
 * Only entries that *differ* from the v7 template are listed.
 */
const MANTINE_8_DEPS: VersionDeps = {
  dependencies: {
    '@mantine/core': '^8.3.15',
    '@mantine/dates': '^8.3.15',
    '@mantine/form': '^8.3.15',
    '@mantine/hooks': '^8.3.15',
    '@mantine/notifications': '^8.3.15',
    react: '^19.1.0',
    'react-dom': '^19.1.0',
  },
  devDependencies: {
    '@types/react': '^19.1.2',
    '@types/react-dom': '^19.1.2',
  },
  removeDeps: [],
  removeDevDeps: [],
  pnpmOverrides: {
    // mantine-react-table@2.0.0-beta.9 has peerDep @mantine/core ^7.9
    // Allow it to work with Mantine 8
    '@mantine/core': '^8.3.15',
    '@mantine/hooks': '^8.3.15',
    '@mantine/dates': '^8.3.15',
  },
};

/**
 * Mantine 7 is the default template — no changes needed.
 */
const MANTINE_7_DEPS: VersionDeps = {
  dependencies: {},
  devDependencies: {},
  removeDeps: [],
  removeDevDeps: [],
};

export function getVersionDeps(version: MantineVersion): VersionDeps {
  return version === '8' ? MANTINE_8_DEPS : MANTINE_7_DEPS;
}

// ---------------------------------------------------------------------------
// package.json patching
// ---------------------------------------------------------------------------

/**
 * Patch a project's package.json to use the specified Mantine version.
 * For Mantine 7, no changes are needed (template is already v7).
 * For Mantine 8, dependencies are upgraded and incompatible ones removed.
 */
export async function patchPackageJson(projectDir: string, version: MantineVersion): Promise<void> {
  if (version === '7') return; // Template is already v7

  const pkgPath = path.join(projectDir, 'package.json');
  const pkg = JSON.parse(await fs.readFile(pkgPath, 'utf-8'));
  const deps = getVersionDeps(version);

  // Update dependencies
  if (pkg.dependencies) {
    for (const [key, val] of Object.entries(deps.dependencies)) {
      if (key in pkg.dependencies || deps.dependencies[key]) {
        pkg.dependencies[key] = val;
      }
    }
    for (const key of deps.removeDeps) {
      delete pkg.dependencies[key];
    }
  }

  // Update devDependencies
  if (pkg.devDependencies) {
    for (const [key, val] of Object.entries(deps.devDependencies)) {
      if (key in pkg.devDependencies || deps.devDependencies[key]) {
        pkg.devDependencies[key] = val;
      }
    }
    for (const key of deps.removeDevDeps) {
      delete pkg.devDependencies[key];
    }
  }

  // Add pnpm overrides to allow mantine-react-table with Mantine 8
  if (deps.pnpmOverrides && Object.keys(deps.pnpmOverrides).length > 0) {
    pkg.pnpm = pkg.pnpm || {};
    pkg.pnpm.overrides = pkg.pnpm.overrides || {};
    Object.assign(pkg.pnpm.overrides, deps.pnpmOverrides);
  }

  await fs.writeFile(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
}

// ---------------------------------------------------------------------------
// Source file patching
// ---------------------------------------------------------------------------

/**
 * Known source-file patches for Mantine 8.
 * Each entry defines a file (relative to project src/) and a find/replace pair.
 */
interface SourcePatch {
  /** File path relative to project's src/ directory */
  relativePath: string;
  /** String to find */
  find: string;
  /** String to replace with */
  replace: string;
}

/**
 * No source patches needed for Mantine 8.
 * mantine-form-zod-resolver works with both Mantine 7 and 8,
 * so we keep using it directly instead of the built-in @mantine/form zodResolver
 * which has type incompatibilities with Zod v4.
 */
const MANTINE_8_SOURCE_PATCHES: SourcePatch[] = [];

/**
 * Apply version-specific source file patches.
 * For Mantine 7, no patches are needed.
 * For Mantine 8, updates import paths and other breaking changes.
 *
 * @param srcDir - The project's src/ directory (e.g., /path/to/project/src)
 */
export async function patchSourceFiles(srcDir: string, version: MantineVersion): Promise<void> {
  if (version === '7') return;

  const patches = MANTINE_8_SOURCE_PATCHES;

  for (const patch of patches) {
    const filePath = path.join(srcDir, patch.relativePath);
    try {
      let content = await fs.readFile(filePath, 'utf-8');
      if (content.includes(patch.find)) {
        content = content.replace(patch.find, patch.replace);
        await fs.writeFile(filePath, content);
      }
    } catch {
      // File may not exist yet (e.g., during integrate before generate runs).
      // Silently skip — the patch will be applied on next regeneration.
    }
  }
}

// ---------------------------------------------------------------------------
// .specstarrc.json management
// ---------------------------------------------------------------------------

const RC_FILENAME = '.specstarrc.json';

/**
 * Read the whole .specstarrc.json.
 *
 * Returns an empty config when the file is absent, unparseable, or not a JSON
 * object — a broken config should degrade to defaults, not abort a generate.
 */
export async function readRc(projectDir: string): Promise<Partial<SpecStarRc>> {
  const rcPath = path.join(projectDir, RC_FILENAME);
  try {
    const parsed: unknown = JSON.parse(await fs.readFile(rcPath, 'utf-8'));
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Partial<SpecStarRc>;
    }
  } catch {
    // File doesn't exist or is invalid
  }
  return {};
}

/**
 * Write the Mantine version choice to .specstarrc.json in the project root.
 *
 * Merges into the existing config rather than replacing it: `integrate` runs
 * against an established project, and a whole-file rewrite would silently drop
 * branding the developer had already configured.
 */
export async function writeVersionConfig(projectDir: string, version: MantineVersion): Promise<void> {
  const rcPath = path.join(projectDir, RC_FILENAME);
  const config: Partial<SpecStarRc> = { ...(await readRc(projectDir)), mantineVersion: version };
  await fs.writeFile(rcPath, JSON.stringify(config, null, 2) + '\n');
}

/**
 * Read the Mantine version from .specstarrc.json.
 * Returns '7' as default if the file doesn't exist or is invalid.
 */
export async function readVersionConfig(projectDir: string): Promise<MantineVersion> {
  const rcPath = path.join(projectDir, RC_FILENAME);
  try {
    const content = await fs.readFile(rcPath, 'utf-8');
    const config = JSON.parse(content) as Partial<SpecStarRc>;
    if (config.mantineVersion === '7' || config.mantineVersion === '8') {
      return config.mantineVersion;
    }
  } catch {
    // File doesn't exist or is invalid
  }
  return '7';
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/**
 * Validate and normalize a Mantine version string from CLI input.
 * Throws if the version is not '7' or '8'.
 */
export function validateMantineVersion(input: string): MantineVersion {
  if (input === '7' || input === '8') return input;
  throw new Error(`Invalid Mantine version "${input}". Must be "7" or "8".`);
}

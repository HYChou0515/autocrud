import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

type PackageJson = {
  version?: unknown;
};

export function resolveCliVersion(packageJsonPath?: string): string {
  const currentFile = fileURLToPath(import.meta.url);
  const defaultPackageJsonPath = path.resolve(path.dirname(currentFile), '..', 'package.json');
  const resolvedPath = packageJsonPath ?? defaultPackageJsonPath;

  const content = fs.readFileSync(resolvedPath, 'utf8');
  const packageJson = JSON.parse(content) as PackageJson;

  if (typeof packageJson.version !== 'string' || packageJson.version.length === 0) {
    throw new Error(`Invalid package.json version at ${resolvedPath}`);
  }

  return packageJson.version;
}

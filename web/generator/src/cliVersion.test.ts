import { describe, it, expect } from 'vitest';
import * as fs from 'fs/promises';
import * as fsSync from 'fs';
import * as path from 'path';
import * as os from 'os';
import { resolveCliVersion } from './cliVersion.js';

describe('resolveCliVersion', () => {
  it('reads version from package.json', async () => {
    const tmpDir = fsSync.mkdtempSync(path.join(os.tmpdir(), 'autocrud-cli-version-'));
    const packageJsonPath = path.join(tmpDir, 'package.json');

    try {
      await fs.writeFile(packageJsonPath, JSON.stringify({ version: '1.2.3-test' }));
      expect(resolveCliVersion(packageJsonPath)).toBe('1.2.3-test');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  it('throws when version is missing', async () => {
    const tmpDir = fsSync.mkdtempSync(path.join(os.tmpdir(), 'autocrud-cli-version-'));
    const packageJsonPath = path.join(tmpDir, 'package.json');

    try {
      await fs.writeFile(packageJsonPath, JSON.stringify({ name: 'autocrud-web-generator' }));
      expect(() => resolveCliVersion(packageJsonPath)).toThrow('Invalid package.json version');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });
});

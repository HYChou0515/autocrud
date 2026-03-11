/**
 * CodeGenerator — orchestrates all code generation from IR Resources.
 *
 * Takes parsed IR Resources and writes generated .ts/.tsx files.
 */

import fs from 'node:fs';
import path from 'node:path';

import type { Resource } from '../types.js';
import { OpenAPIParser } from '../openapi-parser.js';
import { genTypes } from './ts-type.js';
import { genResourcesConfig } from './resources-gen.js';
import { genApiClient, genApiIndex, genBackupApiClient, genMigrateApiClient } from './api-gen.js';
import {
  genListRoute,
  genCreateRoute,
  genDetailRoute,
  genBackupPage,
  genMigratePage,
  genRootIndex,
  genDashboard,
} from './routes-gen.js';

export class CodeGenerator {
  constructor(
    private resources: Resource[],
    private spec: any,
    private ROOT: string,
    private SRC: string,
    private GEN: string,
    private ROUTES: string,
    private basePath: string,
    private parser: OpenAPIParser,
  ) {}

  run() {
    console.log(`📦 Resources: ${this.resources.map((r) => r.name).join(', ')}\n`);
    console.log('📝 Generating files...');

    // types.ts — needs parseField for computing TS types from all schemas
    this.writeFile(
      path.join(this.GEN, 'types.ts'),
      genTypes(this.spec, this.resources, (name, prop, isRequired) => this.parser.parseField(name, prop, isRequired)),
    );

    // resources.ts — resource registry with zod schemas
    this.writeFile(
      path.join(this.GEN, 'resources.ts'),
      genResourcesConfig(this.resources, this.basePath, this.spec, (r) => this.parser.getJobHiddenFields(r)),
    );

    // Per-resource API clients
    for (const r of this.resources) {
      this.writeFile(path.join(this.GEN, 'api', `${r.name}Api.ts`), genApiClient(r, this.basePath));
    }
    this.writeFile(path.join(this.GEN, 'api', 'index.ts'), genApiIndex(this.resources));

    // Backup / restore
    this.writeFile(path.join(this.GEN, 'api', 'backupApi.ts'), genBackupApiClient(this.resources, this.basePath));
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'backup.tsx'), genBackupPage(this.resources));

    // Migrate
    this.writeFile(path.join(this.GEN, 'api', 'migrateApi.ts'), genMigrateApiClient(this.basePath));
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'migrate.tsx'), genMigratePage(this.resources));

    // Root / Dashboard
    this.writeFile(path.join(this.ROUTES, 'index.tsx'), genRootIndex());
    this.writeFile(path.join(this.ROUTES, 'autocrud-admin', 'index.tsx'), genDashboard());

    // Per-resource routes
    for (const r of this.resources) {
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, 'index.tsx'), genListRoute(r));
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, 'create.tsx'), genCreateRoute(r));
      this.writeFile(path.join(this.ROUTES, 'autocrud-admin', r.name, '$resourceId.tsx'), genDetailRoute(r));
    }

    const fileCount = 5 + this.resources.length * 4 + 2 + 2;
    console.log(`\n✨ Done! Generated ${fileCount} files.`);
    console.log('\nNext steps:');
    console.log('  pnpm dev');
  }

  private writeFile(filePath: string, content: string) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`  ✅ ${path.relative(this.ROOT, filePath)}`);
  }
}

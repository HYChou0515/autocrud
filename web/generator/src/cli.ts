#!/usr/bin/env node
import { Command } from 'commander';
import { initProject } from './commands/init.js';
import { generateCode } from './commands/generate.js';
import { integrateProject } from './commands/integrate.js';

const program = new Command();

program
  .name('autocrud-web')
  .description('AutoCRUD Web Code Generator - Generate React frontend from AutoCRUD API')
  .version('0.3.2');

program
  .command('init')
  .description('Initialize a new AutoCRUD Web project')
  .argument('<project-name>', 'Project name')
  .option('-d, --dir <directory>', 'Target directory', '.')
  .option('--include-tests', 'Include test files in generated output', false)
  .action(async (projectName: string, options: { dir: string; includeTests: boolean }) => {
    await initProject(projectName, options.dir, { includeTests: options.includeTests });
  });

program
  .command('generate')
  .description('Generate code from AutoCRUD API OpenAPI spec')
  .option(
    '-u, --url <api-url>',
    'Backend API URL (used to fetch OpenAPI spec and as dev proxy target)',
    'http://localhost:8000',
  )
  .option('-o, --output <directory>', 'Output directory', 'src')
  .option('--openapi-path <path>', 'Path to OpenAPI spec endpoint', '/openapi.json')
  .option('--base-path <path>', 'API base path prefix (auto-detected if omitted)')
  .action(async (options: { url: string; output: string; openapiPath: string; basePath?: string }) => {
    await generateCode(options.url, options.output, {
      openapiPath: options.openapiPath,
      basePath: options.basePath,
    });
  });

program
  .command('integrate')
  .description('Integrate AutoCRUD generated code into an existing React project')
  .option(
    '-u, --url <api-url>',
    'Backend API URL (used to fetch OpenAPI spec and as dev proxy target)',
    'http://localhost:8000',
  )
  .option('-o, --output <directory>', 'Output directory (your src/)', 'src')
  .option('--openapi-path <path>', 'Path to OpenAPI spec endpoint', '/openapi.json')
  .option('--base-path <path>', 'API base path prefix (auto-detected if omitted)')
  .option('--include-tests', 'Include test files in generated output', false)
  .action(
    async (options: { url: string; output: string; openapiPath: string; basePath?: string; includeTests: boolean }) => {
      await integrateProject(options.url, options.output, {
        openapiPath: options.openapiPath,
        basePath: options.basePath,
        includeTests: options.includeTests,
      });
    },
  );

program.parse();

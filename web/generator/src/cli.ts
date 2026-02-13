#!/usr/bin/env node
import { Command } from 'commander';
import { initProject } from './commands/init.js';
import { generateCode } from './commands/generate.js';

const program = new Command();

program
  .name('autocrud-web')
  .description('AutoCRUD Web Code Generator - Generate React frontend from AutoCRUD API')
  .version('0.2.0');

program
  .command('init')
  .description('Initialize a new AutoCRUD Web project')
  .argument('<project-name>', 'Project name')
  .option('-d, --dir <directory>', 'Target directory', '.')
  .action(async (projectName: string, options: { dir: string }) => {
    await initProject(projectName, options.dir);
  });

program
  .command('generate')
  .description('Generate code from AutoCRUD API OpenAPI spec')
  .option('-u, --url <api-url>', 'API base URL', 'http://localhost:8000')
  .option('-o, --output <directory>', 'Output directory', 'src')
  .action(async (options: { url: string; output: string }) => {
    await generateCode(options.url, options.output);
  });

program.parse();

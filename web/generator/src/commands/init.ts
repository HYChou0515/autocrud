import * as fs from 'fs/promises';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export async function initProject(projectName: string, targetDir: string): Promise<void> {
  console.log(`\n🚀 Initializing AutoCRUD Web project: ${projectName}\n`);

  const projectPath = path.join(targetDir, projectName);
  const templatePath = path.join(__dirname, '../../templates/base');

  try {
    // 檢查目錄是否已存在
    try {
      await fs.access(projectPath);
      console.error(`❌ Error: Directory "${projectPath}" already exists`);
      process.exit(1);
    } catch {
      // 目錄不存在，繼續
    }

    // 複製模板
    console.log('📂 Copying template files...');
    await copyDir(templatePath, projectPath);

    // 更新 package.json 的 name
    const pkgPath = path.join(projectPath, 'package.json');
    const pkg = JSON.parse(await fs.readFile(pkgPath, 'utf-8'));
    pkg.name = projectName;
    await fs.writeFile(pkgPath, JSON.stringify(pkg, null, 2));

    console.log('\n✅ Project initialized successfully!\n');
    console.log('📝 Next steps:');
    console.log(`   cd ${projectName}`);
    console.log('   pnpm install');
    console.log('   pnpm generate --url http://your-api-url:8000');
    console.log('   pnpm dev\n');
  } catch (error) {
    console.error('❌ Error initializing project:', error);
    process.exit(1);
  }
}

async function copyDir(src: string, dest: string): Promise<void> {
  await fs.mkdir(dest, { recursive: true });
  const entries = await fs.readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      await copyDir(srcPath, destPath);
    } else {
      await fs.copyFile(srcPath, destPath);
    }
  }
}

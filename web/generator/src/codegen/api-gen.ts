/**
 * Generate API client files (per-resource, backup, migrate, index).
 */

import type { Resource } from '../types.js';
import { toCamel } from '../types.js';

/**
 * Generate an API client module for a single resource.
 */
export function genApiClient(r: Resource, basePath: string): string {
  const base = `${basePath}/${r.name}`;
  const allTypeImports: string[] = [r.schemaName];
  if (r.customCreateActions) {
    for (const action of r.customCreateActions) {
      if (action.bodySchemaName && !allTypeImports.includes(action.bodySchemaName)) {
        const hasOtherParams =
          !!action.pathParams?.length ||
          !!action.queryParams?.length ||
          !!action.inlineBodyParams?.length ||
          !!action.fileParams?.length;
        if (!hasOtherParams) {
          allTypeImports.push(action.bodySchemaName);
        }
      }
    }
  }
  const typeImports = allTypeImports.join(', ');

  const rerunMethod = r.isJob
    ? `
  rerun: (id: string) =>
    client.post<RevisionInfo>(\`\${BASE}/\${id}/rerun\`),
`
    : '';

  const logsMethod = r.isJob
    ? `
  getLogs: (id: string) =>
    client.get<string>(\`\${BASE}/\${id}/logs\`, { transformResponse: [(data: string) => data] }),
`
    : '';

  let customActionMethods = '';
  if (r.customCreateActions) {
    for (const action of r.customCreateActions) {
      const methodName = toCamel(action.operationId);
      const resourcePrefix = `/${r.name}`;
      const suffix = action.path.startsWith(base)
        ? action.path.slice(base.length)
        : action.path.startsWith(resourcePrefix)
          ? action.path.slice(resourcePrefix.length)
          : action.path;

      if (action.bodySchemaName) {
        const hasOtherParams =
          !!action.pathParams?.length ||
          !!action.queryParams?.length ||
          !!action.inlineBodyParams?.length ||
          !!action.fileParams?.length;

        if (!hasOtherParams) {
          customActionMethods += `
  ${methodName}: (data: ${action.bodySchemaName}) =>
    client.post<RevisionInfo>(\`\${BASE}${suffix}\`, data),
`;
          continue;
        }

        const hasPath = !!action.pathParams?.length;
        const hasQuery = !!action.queryParams?.length;
        const hasInlineBody = !!action.inlineBodyParams?.length;
        const hasFile = !!action.fileParams?.length;
        const bodySchemaParamName = action.bodySchemaParamName || 'body';

        const urlExpr = hasPath
          ? '`${BASE}' + suffix.replace(/\{(\w+)\}/g, (_, pname) => `\${allParams['${pname}'] as string}`) + '`'
          : '`${BASE}' + suffix + '`';

        const setupLines: string[] = [];
        let bodyVar = 'null';

        setupLines.push(`    const bodyObj = allParams['${bodySchemaParamName}'] as Record<string, unknown>;`);

        if (hasFile) {
          setupLines.push('    const formData = new FormData();');
          setupLines.push(`    formData.append('${bodySchemaParamName}', JSON.stringify(bodyObj));`);
          if (hasInlineBody) {
            for (const p of action.inlineBodyParams!) {
              setupLines.push(`    formData.append('${p.name}', String(allParams['${p.name}']));`);
            }
          }
          for (const p of action.fileParams!) {
            setupLines.push(
              `    if (allParams['${p.name}'] instanceof File) formData.append('${p.name}', allParams['${p.name}'] as File);`,
            );
          }
          bodyVar = 'formData';
        } else if (hasInlineBody) {
          const ibpEntries = action.inlineBodyParams!.map((p: any) => `'${p.name}': allParams['${p.name}']`).join(', ');
          setupLines.push(`    const data = { '${bodySchemaParamName}': bodyObj, ${ibpEntries} };`);
          bodyVar = 'data';
        } else {
          setupLines.push(`    const data = { '${bodySchemaParamName}': bodyObj };`);
          bodyVar = 'data';
        }

        let configArg = '';
        if (hasQuery) {
          const qpEntries = action.queryParams!.map((p: any) => `${p.name}: allParams['${p.name}']`).join(', ');
          setupLines.push(`    const params = { ${qpEntries} };`);
          configArg = ', { params }';
        }

        const postArgs = `${urlExpr}, ${bodyVar}${configArg}`;
        customActionMethods += `
  ${methodName}: (allParams: Record<string, unknown>) => {
${setupLines.join('\n')}
    return client.post<RevisionInfo>(${postArgs});
  },
`;
        continue;
      }

      // Compositional: build URL, body, and config independently
      const hasPath = !!action.pathParams?.length;
      const hasQuery = !!action.queryParams?.length;
      const hasInlineBody = !!action.inlineBodyParams;
      const hasFile = !!action.fileParams?.length;

      const urlExpr = hasPath
        ? '`${BASE}' + suffix.replace(/\{(\w+)\}/g, (_, pname) => `\${allParams['${pname}'] as string}`) + '`'
        : '`${BASE}' + suffix + '`';

      const bodyLines: string[] = [];
      let bodyVar = 'null';
      if (hasFile) {
        bodyLines.push('    const formData = new FormData();');
        if (hasInlineBody) {
          for (const p of action.inlineBodyParams as any[]) {
            bodyLines.push(`    formData.append('${p.name}', String(allParams['${p.name}']));`);
          }
        }
        for (const p of action.fileParams as any[]) {
          bodyLines.push(
            `    if (allParams['${p.name}'] instanceof File) formData.append('${p.name}', allParams['${p.name}'] as File);`,
          );
        }
        bodyVar = 'formData';
      } else if (hasInlineBody) {
        const ibpEntries = (action.inlineBodyParams as any[])
          .map((p: any) => `${p.name}: allParams['${p.name}']`)
          .join(', ');
        bodyLines.push(`    const data = { ${ibpEntries} };`);
        bodyVar = 'data';
      }

      const configLines: string[] = [];
      let configArg = '';
      if (hasQuery) {
        const qpEntries = action.queryParams!.map((p: any) => `${p.name}: allParams['${p.name}']`).join(', ');
        configLines.push(`    const params = { ${qpEntries} };`);
        configArg = ', { params }';
      }

      const allSetupLines = [...bodyLines, ...configLines];
      if (allSetupLines.length === 0) {
        customActionMethods += `
  ${methodName}: (allParams: Record<string, unknown>) =>
    client.post<RevisionInfo>(${urlExpr}, ${bodyVar}${configArg}),
`;
      } else {
        const postArgs = `${urlExpr}, ${bodyVar}${configArg}`;
        customActionMethods += `
  ${methodName}: (allParams: Record<string, unknown>) => {
${allSetupLines.join('\n')}
    return client.post<RevisionInfo>(${postArgs});
  },
`;
      }
    }
  }

  return `// Auto-generated by AutoCRUD Web Generator
import { client } from '../../lib/client';
import type { ${typeImports} } from '../types';
import type { ResourceMeta, RevisionInfo, FullResource, RevisionListResponse, RevisionListParams, SearchParams } from '../../types/api';

const BASE = '${base}';

export const ${r.camel}Api = {
  create: (data: ${r.schemaName}) =>
    client.post<RevisionInfo>(BASE, data),

  list: (params?: SearchParams & { returns?: string }) =>
    client.get<FullResource<${r.schemaName}>[]>(BASE, { params }),

  count: (params?: SearchParams) =>
    client.get<number>(\`\${BASE}/count\`, { params }),

  get: (id: string, params?: { revision_id?: string; partial?: string[]; returns?: string; include_deleted?: boolean }) =>
    client.get<FullResource<${r.schemaName}>>(\`\${BASE}/\${id}\`, { params }),

  update: (id: string, data: ${r.schemaName}, params?: { change_status?: string; mode?: string }) =>
    client.put<RevisionInfo>(\`\${BASE}/\${id}\`, data, { params }),

  delete: (id: string) =>
    client.delete<ResourceMeta>(\`\${BASE}/\${id}\`),

  permanentlyDelete: (id: string) =>
    client.delete<ResourceMeta>(\`\${BASE}/\${id}/permanently\`),

  restore: (id: string) =>
    client.post<ResourceMeta>(\`\${BASE}/\${id}/restore\`),

  revisionList: (id: string, params?: RevisionListParams) =>
    client.get<RevisionListResponse>(\`\${BASE}/\${id}/revision-list\`, { params }),

  switchRevision: (id: string, revisionId: string) =>
    client.post<ResourceMeta>(\`\${BASE}/\${id}/switch/\${revisionId}\`),
${rerunMethod}${logsMethod}${customActionMethods}};
`;
}

/**
 * Generate the API index barrel export file.
 */
export function genApiIndex(resources: Resource[]): string {
  const exports = resources.map((r) => `export { ${r.camel}Api } from './${r.name}Api';`).join('\n');
  return `// Auto-generated by AutoCRUD Web Generator\n${exports}\nexport { backupApi } from './backupApi';\nexport { migrateApi } from './migrateApi';\n`;
}

/**
 * Generate the backup API client.
 */
export function genBackupApiClient(resources: Resource[], basePath: string): string {
  const bp = basePath;
  const perModel = resources
    .map(
      (r) => `
  /** Export ${r.label} data as .acbak archive */
  export${r.pascal}: (params?: Record<string, unknown>) =>
    client.get(\`${bp}/${r.name}/export\`, { params, responseType: 'blob' }),

  /** Import .acbak archive into ${r.label} */
  import${r.pascal}: (file: File, onDuplicate: OnDuplicate = 'overwrite') => {
    const form = new FormData();
    form.append('file', file);
    return client.post<ImportResult>(\`${bp}/${r.name}/import\`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { on_duplicate: onDuplicate },
    });
  },`,
    )
    .join('\n');

  return `// Auto-generated by AutoCRUD Web Generator
import { client } from '../../lib/client';

export type OnDuplicate = 'overwrite' | 'skip' | 'raise_error';

export interface ImportResult {
  loaded: number;
  skipped: number;
  total: number;
}

export interface GlobalImportResult {
  [model: string]: ImportResult;
}

export const backupApi = {
  /** Download full backup (.acbak) for all models — uses the AutoCRUD global /_backup endpoint */
  exportAll: (models?: string[]) =>
    client.get('${bp}/_backup/export', {
      params: models ? { models } : undefined,
      responseType: 'blob',
    }),

  /** Upload .acbak archive (global import) — uses the AutoCRUD global /_backup endpoint */
  importAll: (file: File, onDuplicate: OnDuplicate = 'overwrite') => {
    const form = new FormData();
    form.append('file', file);
    return client.post<GlobalImportResult>('${bp}/_backup/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { on_duplicate: onDuplicate },
    });
  },
${perModel}
};
`;
}

/**
 * Generate the migrate API client.
 */
export function genMigrateApiClient(basePath: string): string {
  const bp = basePath;
  return `// Auto-generated by AutoCRUD Web Generator
import { getBaseUrl } from '../../lib/client';

/** Progress message for a single resource during migration. */
export interface MigrateProgress {
  resource_id: string;
  status: 'migrating' | 'success' | 'failed' | 'skipped';
  message?: string;
  error?: string;
  timestamp?: string;
}

/** Final summary after migration completes. */
export interface MigrateResult {
  total: number;
  success: number;
  failed: number;
  skipped: number;
  errors: Array<{ resource_id: string; error: string }>;
  timestamp?: string;
}

/**
 * Parse a JSONL streaming response and invoke callbacks for each message.
 *
 * Uses native \`fetch\` instead of Axios because Axios does not support
 * \`ReadableStream\` for JSONL streaming responses.
 *
 * Progress messages (containing \`resource_id\`) are forwarded to \`onProgress\`.
 * The final summary message (containing \`total\`) is returned as the resolved value.
 */
async function streamMigrate(
  url: string,
  onProgress?: (p: MigrateProgress) => void,
  signal?: AbortSignal,
): Promise<MigrateResult> {
  const response = await fetch(url, { method: 'POST', signal });
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    throw new Error(\`HTTP \${response.status}: \${text}\`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: MigrateResult | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\\n');
    buffer = lines.pop()!; // keep the potentially incomplete last line

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const data = JSON.parse(line);
        if ('total' in data && 'success' in data) {
          result = data as MigrateResult;
        } else if (onProgress) {
          onProgress(data as MigrateProgress);
        }
      } catch {
        // skip malformed lines
      }
    }
  }

  // Process any remaining buffer
  if (buffer.trim()) {
    try {
      const data = JSON.parse(buffer);
      if ('total' in data && 'success' in data) {
        result = data as MigrateResult;
      } else if (onProgress) {
        onProgress(data as MigrateProgress);
      }
    } catch {
      // skip
    }
  }

  if (!result) {
    throw new Error('No migration result received from server');
  }
  return result;
}

/**
 * Build the migration URL with optional revision_id query parameter.
 */
function buildMigrateUrl(
  base: string,
  modelName: string,
  action: 'test' | 'execute',
  revisionId?: string | null,
): string {
  const url = \`\${base}/\${modelName}/migrate/\${action}\`;
  if (revisionId) {
    return \`\${url}?revision_id=\${encodeURIComponent(revisionId)}\`;
  }
  return url;
}

/** Revision scope for batch migration. */
export type RevisionScope =
  | null       // current revision only (default)
  | 'all'      // every revision of each resource
  | string;    // specific revision ID

export const migrateApi = {
  /**
   * Test migration (dry run) for a model.
   * No data is written — safe to run on production.
   *
   * @param revisionId - Revision scope: omit/null for current, "all" for every revision, or a specific ID.
   */
  test: (
    modelName: string,
    onProgress?: (p: MigrateProgress) => void,
    signal?: AbortSignal,
    revisionId?: RevisionScope,
  ): Promise<MigrateResult> =>
    streamMigrate(buildMigrateUrl(\`\${getBaseUrl()}${bp}\`, modelName, 'test', revisionId), onProgress, signal),

  /**
   * Execute migration for a model.
   * Migrated data is written back to storage.
   *
   * @param revisionId - Revision scope: omit/null for current, "all" for every revision, or a specific ID.
   */
  execute: (
    modelName: string,
    onProgress?: (p: MigrateProgress) => void,
    signal?: AbortSignal,
    revisionId?: RevisionScope,
  ): Promise<MigrateResult> =>
    streamMigrate(buildMigrateUrl(\`\${getBaseUrl()}${bp}\`, modelName, 'execute', revisionId), onProgress, signal),
};
`;
}

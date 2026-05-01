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
  if (r.customUpdateActions) {
    for (const action of r.customUpdateActions) {
      if (action.bodySchemaName && !allTypeImports.includes(action.bodySchemaName)) {
        allTypeImports.push(action.bodySchemaName);
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

  let customUpdateActionMethods = '';
  if (r.customUpdateActions) {
    for (const action of r.customUpdateActions) {
      const methodName = toCamel(action.operationId);
      // Extract suffix after {resource_id} — e.g. /character/{resource_id}/level-up → /level-up
      const ridMarker = '{resource_id}';
      const ridIdx = action.path.indexOf(ridMarker);
      const suffix = ridIdx >= 0 ? action.path.slice(ridIdx + ridMarker.length) : `/${action.name}`;

      if (action.bodySchemaName && !action.queryParams?.length) {
        // Simple body-only update action
        customUpdateActionMethods += `
  ${methodName}: (id: string, data: ${action.bodySchemaName}) =>
    client.post<RevisionInfo>(\`\${BASE}/\${id}${suffix}\`, data),
`;
      } else if (action.bodySchemaName && action.queryParams?.length) {
        // Body + query params
        const qpEntries = action.queryParams.map((p: any) => `${p.name}: allParams['${p.name}']`).join(', ');
        customUpdateActionMethods += `
  ${methodName}: (id: string, allParams: Record<string, unknown>) => {
    const body = allParams['body'] as ${action.bodySchemaName};
    const params = { ${qpEntries} };
    return client.post<RevisionInfo>(\`\${BASE}/\${id}${suffix}\`, body, { params });
  },
`;
      } else if (action.queryParams?.length) {
        // Query-only, no body
        const qpEntries = action.queryParams.map((p: any) => `${p.name}: allParams['${p.name}']`).join(', ');
        customUpdateActionMethods += `
  ${methodName}: (id: string, allParams: Record<string, unknown>) => {
    const params = { ${qpEntries} };
    return client.post<RevisionInfo>(\`\${BASE}/\${id}${suffix}\`, null, { params });
  },
`;
      } else {
        // No body, no query — simple POST
        customUpdateActionMethods += `
  ${methodName}: (id: string) =>
    client.post<RevisionInfo>(\`\${BASE}/\${id}${suffix}\`),
`;
      }
    }
  }

  return `// Auto-generated by SpecStar Web Generator
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
${rerunMethod}${logsMethod}${customActionMethods}${customUpdateActionMethods}};
`;
}

/**
 * Generate the API index barrel export file.
 */
export function genApiIndex(resources: Resource[]): string {
  const exports = resources.map((r) => `export { ${r.camel}Api } from './${r.name}Api';`).join('\n');
  return `// Auto-generated by SpecStar Web Generator\n${exports}\nexport { backupApi } from './backupApi';\nexport { blobApi } from './blobApi';\nexport { migrateApi } from './migrateApi';\n`;
}

/**
 * Generate the blob upload API client with upload-session support.
 *
 * Endpoints:
 * - POST /blobs/upload — simple single-file upload
 * - POST /blobs/upload-sessions — create an upload session
 * - GET  /blobs/upload-sessions/{upload_id} — poll session status
 * - PUT  /blobs/upload-sessions/{upload_id}/content — upload chunk bytes
 * - POST /blobs/upload-sessions/{upload_id}/finalize — commit to blob store
 * - POST /blobs/upload-sessions/{upload_id}/abort — discard session
 */
export function genBlobApiClient(basePath: string): string {
  const bp = basePath;
  return `// Auto-generated by SpecStar Web Generator
import { client } from '../../lib/client';
import type { BlobUploadSession, BlobFinalizeResult } from '../../types/api';
import type { AxiosProgressEvent } from 'axios';

const BLOBS = '${bp}/blobs';

export const blobApi = {
  /**
   * Simple single-file upload via multipart/form-data.
   * For small files that don't need chunked upload.
   */
  upload: (
    file: File,
    options?: { onUploadProgress?: (e: AxiosProgressEvent) => void; signal?: AbortSignal },
  ) => {
    const form = new FormData();
    form.append('file', file);
    return client.post<{ file_id: string; size: number; content_type: string }>(
      \`\${BLOBS}/upload\`,
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: options?.onUploadProgress,
        signal: options?.signal,
      },
    );
  },

  /**
   * Create an upload session for chunked / parallel uploads.
   */
  createUploadSession: (
    params: { content_type: string; size: number; total_parts?: number },
    signal?: AbortSignal,
  ) => client.post<BlobUploadSession>(\`\${BLOBS}/upload-sessions\`, params, { signal }),

  /**
   * Get the current state of an upload session.
   */
  getUploadSession: (uploadId: string) =>
    client.get<BlobUploadSession>(\`\${BLOBS}/upload-sessions/\${uploadId}\`),

  /**
   * Upload a chunk of bytes to an upload session.
   * Use \`partNumber\` for parallel uploads so the server can reassemble in order.
   */
  uploadChunk: (
    uploadId: string,
    chunk: Blob,
    options?: {
      fileName?: string;
      partNumber?: number;
      onUploadProgress?: (e: AxiosProgressEvent) => void;
      signal?: AbortSignal;
    },
  ) => {
    const form = new FormData();
    form.append('file', chunk, options?.fileName);
    return client.put<BlobUploadSession>(
      \`\${BLOBS}/upload-sessions/\${uploadId}/content\`,
      form,
      {
        params: options?.partNumber != null ? { part_number: options.partNumber } : undefined,
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: options?.onUploadProgress,
        signal: options?.signal,
      },
    );
  },

  /**
   * Finalize an upload session — commits buffered bytes to the blob store.
   * Returns final Binary metadata (file_id, size, content_type).
   */
  finalizeUploadSession: (uploadId: string, signal?: AbortSignal) =>
    client.post<BlobFinalizeResult>(\`\${BLOBS}/upload-sessions/\${uploadId}/finalize\`, null, { signal }),

  /**
   * Abort an upload session — discards all uploaded data.
   */
  abortUploadSession: (uploadId: string) =>
    client.post<void>(\`\${BLOBS}/upload-sessions/\${uploadId}/abort\`),
};
`;
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

  return `// Auto-generated by SpecStar Web Generator
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
  /** Download full backup (.acbak) for all models — uses the SpecStar global /_backup endpoint */
  exportAll: (models?: string[]) =>
    client.get('${bp}/_backup/export', {
      params: models ? { models } : undefined,
      responseType: 'blob',
    }),

  /** Upload .acbak archive (global import) — uses the SpecStar global /_backup endpoint */
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
  return `// Auto-generated by SpecStar Web Generator
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
 * Build the migration URL with query parameters.
 */
function buildMigrateUrl(
  base: string,
  modelName: string,
  action: 'test' | 'execute',
  options?: { revisionId?: RevisionScope; limit?: number; qb?: string },
): string {
  const url = \`\${base}/\${modelName}/migrate/\${action}\`;
  const params = new URLSearchParams();
  if (options?.revisionId) params.set('revision_id', encodeURIComponent(options.revisionId));
  if (options?.limit != null) params.set('limit', String(options.limit));
  if (options?.qb) params.set('qb', options.qb);
  const qs = params.toString();
  return qs ? \`\${url}?\${qs}\` : url;
}

/** Revision scope for batch migration. */
export type RevisionScope =
  | null       // current revision only (default)
  | 'all'      // every revision of each resource
  | string;    // specific revision ID

/** Options for batch migration API calls. */
export interface MigrateOptions {
  /** Callback invoked for each resource as it is migrated. */
  onProgress?: (p: MigrateProgress) => void;
  /** AbortSignal to cancel the migration. */
  signal?: AbortSignal;
  /** Revision scope: omit/null for current, "all" for every revision, or a specific ID. */
  revisionId?: RevisionScope;
  /** Maximum number of resources to migrate. When omitted, the server default (10) is used. */
  limit?: number;
  /** QB expression to filter which resources to migrate. Example: "QB['status'] == 'active'" */
  qb?: string;
}

export const migrateApi = {
  /**
   * Test migration (dry run) for a model.
   * No data is written — safe to run on production.
   */
  test: (
    modelName: string,
    options?: MigrateOptions,
  ): Promise<MigrateResult> =>
    streamMigrate(
      buildMigrateUrl(\`\${getBaseUrl()}${bp}\`, modelName, 'test', options),
      options?.onProgress,
      options?.signal,
    ),

  /**
   * Execute migration for a model.
   * Migrated data is written back to storage.
   */
  execute: (
    modelName: string,
    options?: MigrateOptions,
  ): Promise<MigrateResult> =>
    streamMigrate(
      buildMigrateUrl(\`\${getBaseUrl()}${bp}\`, modelName, 'execute', options),
      options?.onProgress,
      options?.signal,
    ),
};
`;
}

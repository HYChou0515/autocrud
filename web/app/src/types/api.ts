/** Shared AutoCRUD API types - these are the same across all resources */

export interface ResourceMeta {
  resource_id: string;
  current_revision_id: string;
  schema_version: string | null;
  total_revision_count: number;
  created_time: string;
  updated_time: string;
  created_by: string;
  updated_by: string;
  is_deleted: boolean;
  indexed_data?: Record<string, unknown>;
}

export interface RevisionInfo {
  uid: string;
  resource_id: string;
  revision_id: string;
  parent_revision_id: string | null;
  parent_schema_version: string | null;
  schema_version: string | null;
  data_hash: string;
  status: 'draft' | 'stable';
  created_time: string;
  updated_time: string;
  created_by: string;
  updated_by: string;
}

export interface FullResource<T> {
  data: T;
  meta: ResourceMeta;
  revision_info: RevisionInfo;
}

export interface RevisionListResponse {
  meta: ResourceMeta;
  revisions: RevisionInfo[];
}

export interface SearchParams {
  qb?: string;
  is_deleted?: boolean;
  created_time_start?: string;
  created_time_end?: string;
  updated_time_start?: string;
  updated_time_end?: string;
  created_bys?: string[];
  updated_bys?: string[];
  data_conditions?: string;
  conditions?: string;
  sorts?: string;
  limit?: number;
  offset?: number;
  partial?: string[];
}

import type { ResourceMeta, RevisionInfo, FullResource } from '../types/api';
import type { z } from 'zod';

/**
 * Field variant types - allows customization of input component
 * 支援不同的 UI variant
 */
export type FieldVariant = 
  | { type: 'text' }
  | { type: 'textarea'; rows?: number }
  | { type: 'monaco'; language?: string; height?: number }
  | { type: 'markdown'; height?: number }
  | { type: 'number'; min?: number; max?: number; step?: number }
  | { type: 'slider'; sliderMin?: number; sliderMax?: number; step?: number }
  | { type: 'select'; options?: { value: string; label: string }[] }
  | { type: 'checkbox' }
  | { type: 'switch' }
  | { type: 'date' }
  | { type: 'file'; accept?: string; multiple?: boolean }
  | { type: 'json'; height?: number }
  | { type: 'tags'; maxTags?: number; splitChars?: string[] }
  | { type: 'array'; itemType?: 'text' | 'number'; minItems?: number; maxItems?: number }
  | { type: 'union'; variant?: 'radio.group' | 'radio.card' };

/**
 * Reference metadata for fields that point to another resource
 */
export interface FieldRef {
  resource: string;
  type: 'resource_id' | 'revision_id';
  onDelete?: 'dangling' | 'set_null' | 'cascade';
}

/**
 * Resource field definition for meta-programming
 */
export interface ResourceField {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'date' | 'array' | 'object' | 'binary';
  isArray: boolean;
  isRequired: boolean;
  isNullable: boolean;
  // Enum values for select/radio inputs (from OpenAPI enum)
  enumValues?: string[];
  // Variant system - allows post-generation customization
  variant?: FieldVariant;
  // For arrays of typed objects: the item's sub-fields
  itemFields?: ResourceField[];
  // Reference to another resource (from Ref/RefRevision annotations)
  ref?: FieldRef;
}

/**
 * Resource configuration for code generation and runtime
 */
export interface ResourceConfig<T = any> {
  name: string;
  label: string;
  pluralLabel: string;
  schema: string;
  fields: ResourceField[];
  indexedFields?: string[];
  /** Default max depth for form field expansion. Fields deeper than this render as JSON editors. */
  maxFormDepth?: number;
  // Zod schema for validation (generated from OpenAPI)
  zodSchema?: z.ZodObject<any>;
  apiClient: {
    create: (data: T) => Promise<{ data: RevisionInfo }>;
    listFull: (params?: any) => Promise<{ data: FullResource<T>[] }>;
    count: (params?: any) => Promise<{ data: number }>;
    getFull: (id: string, params?: any) => Promise<{ data: FullResource<T> }>;
    update: (id: string, data: T, params?: any) => Promise<{ data: RevisionInfo }>;
    delete: (id: string) => Promise<{ data: ResourceMeta }>;
    restore: (id: string) => Promise<{ data: ResourceMeta }>;
    revisionList: (id: string) => Promise<{ data: { meta: ResourceMeta; revisions: RevisionInfo[] } }>;
  };
}

/**
 * Registry of all resources (generated)
 */
export const resources: Record<string, ResourceConfig> = {};

/**
 * Get resource config by name
 */
export function getResource(name: string): ResourceConfig | undefined {
  return resources[name];
}

/**
 * Get all resource names
 */
export function getResourceNames(): string[] {
  return Object.keys(resources);
}

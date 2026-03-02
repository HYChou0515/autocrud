export interface Revision {
  revision_id?: string;
  uid?: string;
  revision_status?: string;
  status?: string;
  created_time?: string;
  updated_time?: string;
  created_by?: string;
  updated_by?: string;
  parent_revision_id?: string | null;
}

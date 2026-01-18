## Feature Overview

| Feature | Description |
| :--- | :--- |
| ✅ Auto-generation (Schema → API/Storage) | `Schema as Infrastructure`: Automatically generate routes, logic bindings, and storage mappings |
| ✅ Version Control (Revision History) | Draft→Update / Stable→Append, complete parent revision chain |
| ✅ Migration | Functional Converter, Lazy Upgrade on Read + Save |
| ✅ Storage Architecture (Storage) | Hybrid: Meta (SQL/Redis) + Payload (Object Store) + Blob |
| ✅ Scalability (Scale Out) | Use Object Storage with decoupled indexing for easy horizontal scaling |
| ✅ Partial Update (Partial Update / PATCH) | Precise updates with JSON Patch, faster and bandwidth-efficient |
| ✅ Partial Read | Skip unnecessary fields during msgspec decoding for faster performance and reduced bandwidth |
| ✅ GraphQL Integration | Automatically generate Strawberry GraphQL Endpoints |
| ✅ Blob Optimization | BlobStore deduplication and lazy loading |
| ✅ Permission Control (Permissions) | Three-tier RBAC (Global / Model / Resource) with custom checkers |
| ✅ Event Hooks | Customizable Before / After / OnSuccess / OnError for every operation |
| ✅ Route Templates | Standard CRUD routes and plug-in custom endpoints |
| ✅ Search & Index (Search / Index) | Meta Store provides efficient filtering, sorting, pagination, and complex queries |
| ✅ Audit / Logging | Support post-event audit logs and review workflows |
| ✅ Message Queue | Built-in async task processing, treating Jobs as Resources with versioning and state management |

# Archive System Design

## Overview

The archive system implements a **fast-slow architecture** to optimize both write and read performance for resource metadata management. This design separates storage into two tiers:

- **Fast Storage**: Optimized for quick writes (slow search, fast write)
- **Slow Storage**: Optimized for quick searches (fast search, slow write)

## Architecture

### Fast Storage
- **Purpose**: Primary storage for new and recently updated resources
- **Characteristics**:
  - No indexing for maximum write speed
  - Linear search required for queries
  - Immediate availability of new data
  - Lower storage overhead

### Slow Storage
- **Purpose**: Archive storage for stable, less frequently updated resources
- **Characteristics**:
  - Indexed for fast search operations
  - Optimized query performance
  - Higher storage overhead due to indexing
  - Batch processing for efficiency

## Archive Process

The `archive()` method triggers the migration of metadata from fast storage to slow storage based on configurable criteria.

### Selection Criteria

Resources are selected for archiving based on:
1. **Update Time Age**: Resources with the oldest `updated_time` are prioritized
2. **Percentage-based Selection**: A configurable percentage (x%) of the oldest resources
3. **Threshold-based Selection**: Resources older than a specific time threshold

### Archive Operation Flow

1. **Identify Candidates**: Query fast storage for resources meeting archive criteria
2. **Index Creation**: Build search indexes for the selected resources in slow storage
3. **Data Migration**: Move metadata from fast storage to slow storage
4. **Cleanup**: Remove migrated resources from fast storage
5. **Verification**: Ensure data integrity post-migration

## Benefits

### Performance Optimization
- **Write Operations**: New resources are immediately available in fast storage
- **Search Operations**: Archived resources benefit from indexed search capabilities
- **Memory Efficiency**: Reduces active memory footprint in fast storage

### Scalability
- **Horizontal Scaling**: Fast and slow storage can scale independently
- **Cost Optimization**: Archive storage can use cheaper, slower infrastructure
- **Query Performance**: Search operations scale better with indexed slow storage

## Implementation Details

### Storage Interface

```python
class IStorage:
    @abstractmethod
    def list_unarchived(self) -> Collection[str]:
        """Return resource IDs that are in fast storage."""
        
    @abstractmethod
    def archive_resources(self, resource_ids: Collection[str]) -> None:
        """Move resources from fast to slow storage."""
```

### Memory Storage Implementation

The current `MemoryStorage` implementation tracks unarchived resources:

```python
class MemoryStorage(IStorage):
    def __init__(self):
        self.unarchived: set[str] = set()  # Fast storage tracking
        # ... other storage dictionaries
    
    def save_meta(self, resource_id: str, b: bytes) -> None:
        # Save to storage and mark as unarchived (fast storage)
        self.meta[resource_id] = b
        self.unarchived.add(resource_id)
    
    def archive_resources(self, resource_id: str) -> None:
        # Move from fast to slow storage
        self.unarchived.discard(resource_id)
```

## Search Integration

The search system leverages this architecture:

1. **Fast Storage Search**: `search_resources()` queries `list_unarchived()` for active resources
2. **Slow Storage Search**: Future implementation will query indexed slow storage
3. **Unified Results**: Combine results from both storage tiers

## Configuration Options

### Archive Triggers
- **Time-based**: Archive resources older than X days/hours
- **Count-based**: Archive oldest X% of resources when fast storage exceeds threshold
- **Size-based**: Archive when fast storage reaches memory/disk limits

### Archive Policies
- **Incremental**: Archive small batches regularly
- **Bulk**: Archive large batches during low-traffic periods
- **Adaptive**: Adjust archive frequency based on system load

## Future Enhancements

### Database Integration
- **Fast Storage**: Redis, MemoryDB for high-speed operations
- **Slow Storage**: PostgreSQL, Elasticsearch for indexed searches
- **Hybrid Queries**: Federated search across both storage types

### Advanced Indexing
- **Composite Indexes**: Multi-field indexes for complex queries
- **Partial Indexes**: Index only frequently queried subsets
- **Full-text Search**: Index resource content for text searches

### Monitoring and Metrics
- **Archive Efficiency**: Track migration success rates and performance
- **Storage Utilization**: Monitor fast/slow storage usage patterns
- **Query Performance**: Measure search latency across storage tiers

## Best Practices

### When to Archive
1. **Resource Age**: Archive resources not updated for 30+ days
2. **Query Patterns**: Archive resources rarely accessed
3. **Storage Pressure**: Archive when fast storage reaches 80% capacity

### Archive Frequency
1. **Low Traffic**: Daily archive during off-peak hours
2. **High Traffic**: Continuous micro-batching
3. **Burst Traffic**: Emergency archive during traffic spikes

### Data Integrity
1. **Validation**: Verify data consistency post-migration
2. **Rollback**: Maintain ability to restore from slow to fast storage
3. **Backup**: Regular backups of both storage tiers

## Conclusion

The archive system provides a foundation for scalable resource management by intelligently partitioning data based on access patterns and age. This fast-slow architecture ensures optimal performance for both write-heavy and read-heavy workloads while maintaining system efficiency as data volume grows.

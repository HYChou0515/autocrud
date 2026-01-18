---
title: Benchmarks
description: AutoCRUD Performance Testing and Benchmarks
---

# Performance Benchmarks

AutoCRUD performance results and optimization recommendations.

## Performance Overview

AutoCRUD uses `msgspec` as the serialization engine, delivering significant performance improvements compared to Pydantic.

### Serialization Performance

| Operation  | msgspec | Pydantic | Improvement |
| ---------- | ------- | -------- | ----------- |
| Encode     | 1.2 μs  | 3.5 μs   | **2.9x**    |
| Decode     | 0.8 μs  | 2.8 μs   | **3.5x**    |
| Validation | 0.5 μs  | 2.1 μs   | **4.2x**    |

!!! info "Test Environment"
    - CPU: Intel i7-12700K
    - RAM: 32GB DDR4
    - Python: 3.11
    - Test data: complex objects with 20 fields

## Storage Performance

### Meta Store Query Performance

Using PostgreSQL as the Meta Store:

| Operation                 | Latency (p50) | Latency (p95) | Latency (p99) |
| ------------------------- | ------------- | ------------- | ------------- |
| Single record query       | 2ms           | 5ms           | 8ms           |
| Batch query (100 records) | 15ms          | 25ms          | 35ms          |
| Indexed search            | 8ms           | 15ms          | 22ms          |
| Complex filtering         | 12ms          | 20ms          | 30ms          |

### Resource Store Performance

Using S3 as the Resource Store:

| Operation                 | Latency (p50) | Latency (p95) | Throughput |
| ------------------------- | ------------- | ------------- | ---------- |
| Small object read (<1KB)  | 25ms          | 45ms          | 2000 ops/s |
| Medium object read (10KB) | 30ms          | 55ms          | 1500 ops/s |
| Large object read (1MB)   | 80ms          | 150ms         | 500 ops/s  |
| Write                     | 35ms          | 60ms          | 1000 ops/s |

## Partial Read/Write Performance

The Partial Read feature significantly reduces data transfer and processing time:

| Scenario                      | Full Read | Partial Read | Savings |
| ----------------------------- | --------- | ------------ | ------- |
| 50-field model, read 5 fields | 1.2ms     | 0.3ms        | **75%** |
| With large binary fields      | 15ms      | 2ms          | **87%** |
| Deeply nested structures      | 3.5ms     | 0.8ms        | **77%** |

## Version Control Performance

| Operation                           | Latency |
| ----------------------------------- | ------- |
| Create new revision                 | 8ms     |
| Query revision list (100 revisions) | 12ms    |
| Switch revision                     | 15ms    |
| Compare revisions                   | 5ms     |

## Best Practices

### 1. Use Indexes Wisely

Only create indexes for fields that need to be searched:

```python
# ✅ Good practice
crud.add_model(
    User,
    indexed_fields=[
        ("email", str),      # Required for search
        ("status", str),     # Required for filtering
    ]
)

# ❌ Avoid over-indexing
crud.add_model(
    User,
    indexed_fields=[
        ("email", str),
        ("name", str),
        ("bio", str),        # Large text that does not need to be searched
        ("avatar", bytes),   # Binary data should not be indexed
    ]
)
```

### 2. Use Partial Read

Only read the fields you need:

```python
# ✅ Good practice
client.get(
    f"/user/{user_id}/partial",
    json={"fields": ["name", "email"]}
)

# ❌ Avoid reading the entire object
client.get(f"/user/{user_id}/data")
```

### 3. Batch Operations

Use batch operations to reduce network round trips:

```python
# ✅ Batch read
client.get(
    "/user/data",
    json={"resource_ids": [id1, id2, id3]}
)

# ❌ Read one by one
for user_id in user_ids:
    client.get(f"/user/{user_id}/data")
```

### 4. Choose the Right Storage Backend

| Use Case                     | Recommended Configuration |
| ---------------------------- | ------------------------- |
| Small projects / development | Memory / Disk Storage     |
| Medium-sized projects        | PostgreSQL + Local FS     |
| Large projects / production  | PostgreSQL + S3           |
| High-concurrency reads       | Redis + S3 + CDN          |

## Performance Monitoring

### Enable Performance Tracing

```python
from autocrud import AutoCRUD
from autocrud.util.profiler import enable_profiling

crud = AutoCRUD()
enable_profiling(crud)  # Enable performance profiling
```

### View Statistics

```python
from autocrud.util.profiler import get_stats

stats = get_stats()
print(f"Average read latency: {stats.read_latency_avg}ms")
print(f"Average write latency: {stats.write_latency_avg}ms")
print(f"Cache hit rate: {stats.cache_hit_rate}%")
```

## Load Testing

See the load testing scripts in the project:

* [scripts/run_benchmarks.py](https://github.com/HYChou0515/autocrud/blob/master/scripts/run_benchmarks.py)

Run the benchmarks:

```bash
uv run python scripts/run_benchmarks.py
```

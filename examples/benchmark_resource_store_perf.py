import datetime as dt
import time
import shutil
from pathlib import Path
from uuid import uuid4
import io
import os
import traceback

try:
    import matplotlib.pyplot as plt
    import pandas as pd
    import seaborn as sns

    HAS_PLOT_DEPS = True
except ImportError:
    HAS_PLOT_DEPS = False
    print("Warning: matplotlib and pandas not found. PNG generation will be skipped.")

import json

from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.types import RevisionInfo, RevisionStatus

# Try importing S3 components
try:
    from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
    from autocrud.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
    from autocrud.resource_manager.resource_store.cache import MemoryCache
    import boto3
    from botocore.exceptions import ClientError

    S3_IMP_AVAILABLE = True
except ImportError:
    S3_IMP_AVAILABLE = False
    print("Warning: S3 components or dependencies (boto3) not found.")


def get_resource_store(store_type: str, tmpdir: Path):
    """Factory for resource stores."""
    encoding = Encoding.json  # Using JSON for standard benchmark

    if store_type == "memory":
        return MemoryResourceStore(encoding=encoding)

    if store_type == "disk":
        return DiskResourceStore(encoding=encoding, rootdir=tmpdir)

    if store_type == "s3":
        if not S3_IMP_AVAILABLE:
            return None
        # Default MinIO configuration
        endpoint = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
        bucket = os.environ.get("S3_BUCKET", "benchmark-autocrud")
        prefix = f"bench_{tmpdir.name}/"

        # Check connection
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
                aws_secret_access_key=os.environ.get(
                    "AWS_SECRET_ACCESS_KEY", "minioadmin"
                ),
            )
            # Create bucket if not exists
            try:
                s3.head_bucket(Bucket=bucket)
            except ClientError:
                s3.create_bucket(Bucket=bucket)
        except Exception as e:
            print(
                f"Skipping S3 store: Could not connect to S3/MinIO at {endpoint}: {e}"
            )
            return None

        return S3ResourceStore(
            encoding=encoding,
            endpoint_url=endpoint,
            bucket=bucket,
            prefix=prefix,
        )

    if store_type == "cached_s3":
        if not S3_IMP_AVAILABLE:
            return None
        endpoint = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
        bucket = os.environ.get("S3_BUCKET", "benchmark-autocrud")
        prefix = f"bench_cached_{tmpdir.name}/"

        # Check connection (reuse logic or trust S3 Store check)
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
                aws_secret_access_key=os.environ.get(
                    "AWS_SECRET_ACCESS_KEY", "minioadmin"
                ),
            )
            try:
                s3.head_bucket(Bucket=bucket)
            except ClientError:
                s3.create_bucket(Bucket=bucket)
        except Exception as e:
            print(
                f"Skipping Cached S3 store: Could not connect to S3/MinIO at {endpoint}: {e}"
            )
            return None

        return CachedS3ResourceStore(
            caches=[MemoryCache()],
            encoding=encoding,
            endpoint_url=endpoint,
            bucket=bucket,
            prefix=prefix,
            ttl_draft=60,
            ttl_stable=300,
        )

    raise ValueError(f"Unknown store type: {store_type}")


def run_benchmark():
    data_file = Path("benchmark_resource_store_data.json")
    results = []

    # Clean previous results if desired, or load them to append?
    # For now, let's overwrite for clean run each time or append.
    # The reference script loads existing. I'll do the same.
    if data_file.exists():
        print(f"Loading existing benchmark data from {data_file}...")
        try:
            with open(data_file, "r") as f:
                results = json.load(f)
        except Exception as e:
            print(f"Failed to load benchmark data: {e}")
            results = []

    # If results are empty, or we want to force re-run, we define stores
    # Here we just re-run if we want. We'll simply append new runs.
    # To avoid duplicates, maybe clear results for this run session.
    results = []

    store_types = [
        "memory",
        "disk",
        "s3",
        "cached_s3",
    ]

    # Scenarios: (Number of Items, Data Size in Bytes)
    scenarios = [
        (100, 1024),  # 100 items, 1KB each
        (1000, 1024),  # 1000 items, 1KB each
        (50, 1024 * 1024),  # 50 items, 1MB each
        (100, 1024 * 1024),  # 100 items, 1MB each
    ]

    base_tmp_dir = Path("./benchmark_rs_tmp")
    if base_tmp_dir.exists():
        shutil.rmtree(base_tmp_dir)
    base_tmp_dir.mkdir()

    print(
        f"{'Store Type':<15} | {'Op Type':<15} | {'Count':<10} | {'Size':<10} | {'Time (ms)':<10} | {'QPS':<10}"
    )
    print("-" * 90)

    try:
        for store_type in store_types:
            for count, size in scenarios:
                run_dir = base_tmp_dir / f"{store_type}_{count}_{size}"
                run_dir.mkdir(parents=True, exist_ok=True)

                store = get_resource_store(store_type, run_dir)
                if store is None:
                    continue

                # Cleanup S3 if possible? No easy way unless we list and delete.
                # using unique prefix per run handles collision.

                # Generate Data
                items = []
                payload = b"x" * size
                now = dt.datetime.now(dt.timezone.utc)
                for _ in range(count):
                    rid = str(uuid4())
                    revid = "rev_1"
                    info = RevisionInfo(
                        uid=uuid4(),
                        resource_id=rid,
                        revision_id=revid,
                        schema_version="1.0",
                        status=RevisionStatus.stable,
                        created_time=now,
                        updated_time=now,
                        created_by="bench",
                        updated_by="bench",
                        parent_revision_id=None,
                        data_hash="fake_hash",
                    )
                    items.append(info)

                # 1. Write Benchmark
                start_time = time.perf_counter()
                for info in items:
                    data_stream = io.BytesIO(payload)
                    store.save(info, data_stream)
                end_time = time.perf_counter()

                write_time = end_time - start_time
                write_time_ms = write_time * 1000
                write_qps = count / write_time if write_time > 0 else 0

                print(
                    f"{store_type:<15} | {'Write':<15} | {count:<10} | {size:<10} | {write_time_ms:<10.2f} | {write_qps:<10.2f}"
                )

                results.append(
                    {
                        "Store Type": store_type,
                        "Op Type": "Write",
                        "Count": count,
                        "Data Size": size,
                        "Time (ms)": write_time_ms,
                        "QPS": write_qps,
                    }
                )

                # Sleep to allow async flushes or consistency settling if any
                time.sleep(0.5)

                # 2. Exists Benchmark
                start_time = time.perf_counter()
                for info in items:
                    store.exists(
                        info.resource_id, info.revision_id, info.schema_version
                    )
                end_time = time.perf_counter()

                exists_time = end_time - start_time
                exists_time_ms = exists_time * 1000
                exists_qps = count / exists_time if exists_time > 0 else 0

                print(
                    f"{store_type:<15} | {'Exists':<15} | {count:<10} | {size:<10} | {exists_time_ms:<10.2f} | {exists_qps:<10.2f}"
                )

                results.append(
                    {
                        "Store Type": store_type,
                        "Op Type": "Exists",
                        "Count": count,
                        "Data Size": size,
                        "Time (ms)": exists_time_ms,
                        "QPS": exists_qps,
                    }
                )

                # 3. Read Benchmark (First Pass / Cold if applicable)
                # For Disk/Memory it's same. For CachedS3, first read fetches from S3 and populates cache.
                start_time = time.perf_counter()
                for info in items:
                    with store.get_data_bytes(
                        info.resource_id, info.revision_id, info.schema_version
                    ) as f:
                        _ = f.read()
                end_time = time.perf_counter()

                read_time = end_time - start_time
                read_time_ms = read_time * 1000
                read_qps = count / read_time if read_time > 0 else 0

                print(
                    f"{store_type:<15} | {'Read (1st)':<15} | {count:<10} | {size:<10} | {read_time_ms:<10.2f} | {read_qps:<10.2f}"
                )

                results.append(
                    {
                        "Store Type": store_type,
                        "Op Type": "Read (1st)",
                        "Count": count,
                        "Data Size": size,
                        "Time (ms)": read_time_ms,
                        "QPS": read_qps,
                    }
                )

                # 4. Read Benchmark (Second Pass / Warm)
                start_time = time.perf_counter()
                for info in items:
                    with store.get_data_bytes(
                        info.resource_id, info.revision_id, info.schema_version
                    ) as f:
                        _ = f.read()
                end_time = time.perf_counter()

                read2_time = end_time - start_time
                read2_time_ms = read2_time * 1000
                read2_qps = count / read2_time if read2_time > 0 else 0

                print(
                    f"{store_type:<15} | {'Read (2nd)':<15} | {count:<10} | {size:<10} | {read2_time_ms:<10.2f} | {read2_qps:<10.2f}"
                )

                results.append(
                    {
                        "Store Type": store_type,
                        "Op Type": "Read (2nd)",
                        "Count": count,
                        "Data Size": size,
                        "Time (ms)": read2_time_ms,
                        "QPS": read2_qps,
                    }
                )

                # Cleanup manual if needed (store.cleanup() is custom in some tests)
                if hasattr(store, "cleanup"):
                    try:
                        store.cleanup()
                    except Exception:
                        pass
                elif hasattr(store, "close"):
                    store.close()

    except KeyboardInterrupt:
        print("\nAborted by user.")
    except Exception:
        traceback.print_exc()
    finally:
        if base_tmp_dir.exists():
            shutil.rmtree(base_tmp_dir)

    # Save results
    with open(data_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nBenchmark data saved to {data_file}")

    # --- Generate Outputs ---

    md_lines = ["# Resource Store Benchmark Results\n", "\n"]
    md_lines.append(f"Date: {dt.datetime.now().isoformat()}\n")

    if HAS_PLOT_DEPS and results:
        df = pd.DataFrame(results)
        df["Scenario"] = (
            df["Count"].astype(str) + " x " + df["Data Size"].astype(str) + "B"
        )

        sns.set_theme(style="whitegrid")

        op_types = df["Op Type"].unique()
        print("\nGenerating charts...")

        # One bar chart per Op Type
        fig, axes = plt.subplots(
            len(op_types), 1, figsize=(10, 5 * len(op_types)), constrained_layout=True
        )
        if len(op_types) == 1:
            axes = [axes]

        for i, op_type in enumerate(op_types):
            ax = axes[i]
            data_subset = df[df["Op Type"] == op_type]

            sns.barplot(
                data=data_subset,
                x="Scenario",
                y="QPS",
                hue="Store Type",
                ax=ax,
                palette="viridis",
            )
            ax.set_title(f"QPS - {op_type}")
            ax.set_ylabel("QPS (Higher is better)")
            ax.set_yscale("log")
            ax.set_xlabel("Scenario (Items x Size)")

        filename = "benchmark_resource_store_chart.png"
        plt.savefig(filename)
        print(f"  -> {filename}")
        plt.close()

        md_lines.append(f"\n![Benchmark Chart](./{filename})\n")

        # Detailed Tables
        for op_type in op_types:
            md_lines.append(f"\n### Details: {op_type}\n")
            md_lines.append(
                "| Store Type | Scenario | Count | Size | Time (ms) | QPS |"
            )
            md_lines.append("|---|---|---|---|---|---|")

            data_subset = df[df["Op Type"] == op_type].sort_values(
                by=["Data Size", "QPS"], ascending=[True, False]
            )

            for _, row in data_subset.iterrows():
                md_lines.append(
                    f"| {row['Store Type']} | {row['Scenario']} | {row['Count']} | {row['Data Size']} | {row['Time (ms)']:.2f} | {row['QPS']:.2f} |"
                )

    else:
        # Fallback table
        md_lines.append("| Store Type | Op Type | Count | Size | Time (ms) | QPS |")
        md_lines.append("|---|---|---|---|---|---|")
        for r in results:
            md_lines.append(
                f"| {r['Store Type']} | {r['Op Type']} | {r['Count']} | {r['Data Size']} | {r['Time (ms)']:.2f} | {r['QPS']:.2f} |"
            )

    output_md = "benchmark_resource_store_results.md"
    with open(output_md, "w") as f:
        f.writelines([line + "\n" for line in md_lines])
    print(f"\nUpdated {output_md}")


if __name__ == "__main__":
    run_benchmark()

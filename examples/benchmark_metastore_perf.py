import datetime as dt
import time
import shutil
from pathlib import Path
from uuid import uuid4
import statistics

try:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    import pandas as pd
    import seaborn as sns

    HAS_PLOT_DEPS = True
except ImportError:
    HAS_PLOT_DEPS = False
    print("Warning: matplotlib and pandas not found. PNG generation will be skipped.")

import json
import psycopg2
import redis
from autocrud.types import (
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortKey,
    ResourceMetaSortDirection,
    DataSearchCondition,
    DataSearchOperator,
)
from autocrud.resource_manager.meta_store.df import DFMemoryMetaStore
from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
from autocrud.resource_manager.meta_store.redis import RedisMetaStore
from autocrud.resource_manager.meta_store.simple import (
    DiskMetaStore,
    MemoryMetaStore,
)
from autocrud.resource_manager.meta_store.sqlite3 import (
    FileSqliteMetaStore,
    MemorySqliteMetaStore,
)

# --- Helpers adapted from test_resource_manager.py ---


def reset_and_get_pg_dsn():
    pg_dsn = "postgresql://admin:password@localhost:5432/your_database"
    try:
        pg_conn = psycopg2.connect(pg_dsn)
        with pg_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS resource_meta;")
            pg_conn.commit()
        pg_conn.close()
    except Exception as e:
        print(f"Warning: Could not connect to Postgres: {e}")
        return None
    return pg_dsn


def reset_and_get_redis_url():
    redis_url = "redis://localhost:6379/0"
    try:
        client = redis.Redis.from_url(redis_url)
        client.flushall()
        client.close()
    except Exception as e:
        print(f"Warning: Could not connect to Redis: {e}")
        return None
    return redis_url


def get_meta_store(store_type: str, tmpdir: Path):
    """Factory for meta stores."""
    if store_type == "memory":
        return MemoryMetaStore(encoding="msgpack")

    if store_type == "dfm":
        return DFMemoryMetaStore(encoding="msgpack")

    if store_type == "sql3-mem":
        return MemorySqliteMetaStore(encoding="msgpack")

    if store_type == "memory-pg":
        pg_dsn = reset_and_get_pg_dsn()
        if not pg_dsn:
            return None
        return FastSlowMetaStore(
            fast_store=MemoryMetaStore(encoding="msgpack"),
            slow_store=PostgresMetaStore(
                pg_dsn=pg_dsn,
                encoding="msgpack",
            ),
        )

    if store_type == "sql3-file":
        return FileSqliteMetaStore(db_filepath=tmpdir / "meta.db", encoding="msgpack")

    if store_type == "nfs-sql3-file":
        nfs_base = Path("/home/hychou/Disk/K/test")
        # Use the tmpdir name (e.g. nfs-sql3-file_1000) to separate runs
        nfs_run_dir = nfs_base / tmpdir.name
        # if nfs_run_dir.exists():
        #     shutil.rmtree(nfs_run_dir)
        # nfs_run_dir.mkdir(parents=True, exist_ok=True)
        return FileSqliteMetaStore(
            db_filepath=nfs_run_dir / "meta.db", encoding="msgpack"
        )

    if store_type == "disk-sql3file":
        d = tmpdir / "disk_sql3_data"
        d.mkdir(exist_ok=True)
        return FastSlowMetaStore(
            fast_store=DiskMetaStore(encoding="msgpack", rootdir=d),
            slow_store=FileSqliteMetaStore(
                db_filepath=d / "meta.db",
                encoding="msgpack",
            ),
        )

    if store_type == "redis":
        redis_url = reset_and_get_redis_url()
        if not redis_url:
            return None
        return RedisMetaStore(
            redis_url=redis_url,
            encoding="msgpack",
            prefix=f"bench_{store_type}",
        )

    if store_type == "redis-pg":
        redis_url = reset_and_get_redis_url()
        pg_dsn = reset_and_get_pg_dsn()
        if not redis_url or not pg_dsn:
            return None
        return FastSlowMetaStore(
            fast_store=RedisMetaStore(
                redis_url=redis_url,
                encoding="msgpack",
                prefix=f"bench_{store_type}",
            ),
            slow_store=PostgresMetaStore(
                pg_dsn=pg_dsn,
                encoding="msgpack",
            ),
        )

    if store_type == "redis-sql3file":
        redis_url = reset_and_get_redis_url()
        if not redis_url:
            return None
        return FastSlowMetaStore(
            fast_store=RedisMetaStore(
                redis_url=redis_url,
                encoding="msgpack",
                prefix=f"bench_{store_type}",
            ),
            slow_store=FileSqliteMetaStore(
                db_filepath=tmpdir / "meta.db",
                encoding="msgpack",
            ),
        )

    if store_type == "memory-sql3file":
        return FastSlowMetaStore(
            fast_store=MemoryMetaStore(encoding="msgpack"),
            slow_store=FileSqliteMetaStore(
                db_filepath=tmpdir / "meta.db",
                encoding="msgpack",
            ),
        )

    if store_type == "disk":
        d = tmpdir / "disk_data"
        d.mkdir(exist_ok=True)
        return DiskMetaStore(encoding="msgpack", rootdir=d)

    if store_type == "pg":
        pg_dsn = reset_and_get_pg_dsn()
        if not pg_dsn:
            return None
        return PostgresMetaStore(
            pg_dsn=pg_dsn,
            encoding="msgpack",
        )

    raise ValueError(f"Unknown store type: {store_type}")


# --- Benchmark Logic ---


def generate_metas(count: int, start_time: dt.datetime):
    metas = []
    for i in range(count):
        # Add indexed data for searching
        # Creating a distribution where "category" is "A" for every 10th item, "B" for others
        # "value" is the index i
        indexed_data = {
            "category": "A" if i % 10 == 0 else "B",
            "value": i,
            "tags": ["tag1", "tag2"] if i % 2 == 0 else ["tag3"],
        }

        meta = ResourceMeta(
            resource_id=str(uuid4()),
            current_revision_id=str(uuid4()),
            total_revision_count=1,
            created_time=start_time + dt.timedelta(seconds=i),
            created_by="benchmark",
            updated_time=start_time + dt.timedelta(seconds=i),
            updated_by="benchmark",
            indexed_data=indexed_data,
        )
        metas.append(meta)
    return metas


def run_benchmark():
    data_file = Path("benchmark_data.json")
    results = []

    if data_file.exists():
        print(f"Loading existing benchmark data from {data_file}...")
        try:
            with open(data_file, "r") as f:
                results = json.load(f)
        except Exception as e:
            print(f"Failed to load benchmark data: {e}")
            results = []

    if not results:
        # Run Benchmark Logic if no data loaded
        store_types = [
            "memory",
            "memory-pg",
            "memory-sql3file",
            "sql3-mem",
            "sql3-file",
            "redis-sql3file",
            "disk-sql3file",
            "redis",
            # "dfm",
            "disk",
            "redis-pg",
            "pg",
            # "nfs-sql3-file",
        ]

        # Scenarios: (Total Data Size, Search Result Size)
        scenarios = [
            (1000, 100),
            (5000, 500),
            # (10000, 1000),
        ]

        base_tmp_dir = Path("./benchmark_tmp")
        if base_tmp_dir.exists():
            shutil.rmtree(base_tmp_dir)
        base_tmp_dir.mkdir()

        print(
            f"{'Store Type':<15} | {'Query Type':<15} | {'Total':<10} | {'Read':<10} | {'Time (ms)':<10} | {'QPS':<10}"
        )
        print("-" * 85)

        try:
            for store_type in store_types:
                for total_size, read_size in scenarios:
                    if total_size < read_size:
                        continue

                    # Prepare temporary directory for this run
                    run_dir = base_tmp_dir / f"{store_type}_{total_size}"
                    run_dir.mkdir(parents=True, exist_ok=True)

                    store = get_meta_store(store_type, run_dir)
                    if store is None:
                        print(f"Skipping {store_type} (connection failed)")
                        continue

                    # Generate Data
                    start_dt = dt.datetime(2023, 1, 1)
                    metas = generate_metas(total_size, start_dt)

                    if store_type == "nfs-sql3-file":
                        ...
                    else:
                        # Write Data (Pre-fill & Benchmark)
                        st_write = time.perf_counter()
                        for meta in metas:
                            store[meta.resource_id] = meta
                        ed_write = time.perf_counter()

                    write_time = ed_write - st_write
                    write_time_ms = write_time * 1000
                    write_qps = total_size / write_time if write_time > 0 else 0

                    print(
                        f"{store_type:<15} | {'Write':<15} | {total_size:<10} | {total_size:<10} | {write_time_ms:<10.2f} | {write_qps:<10.2f}"
                    )

                    results.append(
                        {
                            "Store Type": store_type,
                            "Query Type": "Write",
                            "Total Size": total_size,
                            "Read Size": total_size,
                            "Time (ms)": write_time_ms,
                            "QPS": write_qps,
                        }
                    )

                    # Force sync for FastSlow stores
                    if hasattr(store, "force_sync"):
                        store.force_sync()
                    elif hasattr(store, "_sync_fast_to_slow"):
                        store._sync_fast_to_slow()

                    time.sleep(0.5)

                    queries = []

                    # 1. Time Range Query
                    start_idx = (total_size - read_size) // 2
                    end_idx = start_idx + read_size
                    target_slice = metas[start_idx:end_idx]

                    time_query = ResourceMetaSearchQuery(
                        limit=10000,
                        created_time_start=target_slice[0].created_time
                        - dt.timedelta(microseconds=1),
                        created_time_end=target_slice[-1].created_time
                        + dt.timedelta(microseconds=1),
                        sorts=[
                            ResourceMetaSearchSort(
                                key=ResourceMetaSortKey.created_time,
                                direction=ResourceMetaSortDirection.ascending,
                            )
                        ],
                    )
                    queries.append(("Time Range", time_query))

                    # 2. Data Condition Query (Exact Match)
                    data_query = ResourceMetaSearchQuery(
                        limit=10000,
                        data_conditions=[
                            DataSearchCondition(
                                field_path="category",
                                operator=DataSearchOperator.equals,
                                value="A",
                            )
                        ],
                        sorts=[
                            ResourceMetaSearchSort(
                                key=ResourceMetaSortKey.created_time,
                                direction=ResourceMetaSortDirection.ascending,
                            )
                        ],
                    )
                    queries.append(("Data Cond (Eq)", data_query))

                    # 3. Mixed Conditions (Meta + Data)
                    mixed_query = ResourceMetaSearchQuery(
                        limit=10000,
                        created_time_start=target_slice[0].created_time
                        - dt.timedelta(microseconds=1),
                        created_time_end=target_slice[-1].created_time
                        + dt.timedelta(microseconds=1),
                        data_conditions=[
                            DataSearchCondition(
                                field_path="category",
                                operator=DataSearchOperator.equals,
                                value="A",
                            )
                        ],
                        sorts=[
                            ResourceMetaSearchSort(
                                key=ResourceMetaSortKey.created_time,
                                direction=ResourceMetaSortDirection.ascending,
                            )
                        ],
                    )
                    queries.append(("Mixed Cond", mixed_query))

                    for q_name, query in queries:
                        iterations = 5
                        times = []
                        result_count = 0
                        import subprocess as sp

                        if store_type == "nfs-sql3-file":
                            sp.run(
                                "sudo umount -f -l /mnt/nfs/marbles/kingston500",
                                shell=True,
                            )
                            time.sleep(2)
                            sp.run("sudo mount -a", shell=True)
                            time.sleep(2)
                        for _ in range(iterations):
                            st = time.perf_counter()
                            res = list(store.iter_search(query))
                            ed = time.perf_counter()
                            times.append(ed - st)
                            result_count = len(res)

                        med_time = statistics.median(times)
                        med_time_ms = med_time * 1000
                        qps = 1.0 / med_time if med_time > 0 else 0

                        print(
                            f"{store_type:<15} | {q_name:<15} | {total_size:<10} | {result_count:<10} | {med_time_ms:<10.2f} | {qps:<10.2f}"
                        )

                        results.append(
                            {
                                "Store Type": store_type,
                                "Query Type": q_name,
                                "Total Size": total_size,
                                "Read Size": result_count,
                                "Time (ms)": med_time_ms,
                                "QPS": qps,
                            }
                        )

                    if hasattr(store, "close"):
                        store.close()

        finally:
            if base_tmp_dir.exists():
                shutil.rmtree(base_tmp_dir)

        # Save results for future runs
        with open(data_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nBenchmark data saved to {data_file}")

    # --- Generate Outputs ---

    md_lines = ["# MetaStore Benchmark Results\n", "\n"]
    md_lines.append(f"Date: {dt.datetime.now().isoformat()}\n")

    if HAS_PLOT_DEPS and results:
        df = pd.DataFrame(results)

        # Set theme
        sns.set_theme(style="white")

        query_types = df["Query Type"].unique()
        print("\nGenerating combined Heatmap report:")

        # Combine all heatmaps into one figure
        num_q = len(query_types)
        fig, axes = plt.subplots(1, num_q, figsize=(6 * num_q, 10), sharey=True)
        if num_q == 1:
            axes = [axes]

        # Consistent Y-axis order based on Harmonic Mean of Normalized Scores
        # Strategy: "Strict Balance" (The chain is as strong as its weakest link)
        # Harmonic mean is very sensitive to low values. A single bad category significantly pulls down the score.

        # 1. Identify Scenarios and Create Pivot Table
        df["Scenario"] = df["Query Type"] + "_" + df["Total Size"].astype(str)
        pivot_qps = df.pivot(index="Store Type", columns="Scenario", values="QPS")

        # 2. Normalize Scores (Relative to Best Non-Mem in each scenario)
        norm_scores = pd.DataFrame(index=pivot_qps.index, columns=pivot_qps.columns)

        for col in pivot_qps.columns:
            start_max_val = pivot_qps[col].max()

            if start_max_val > 0:
                norm_scores[col] = pivot_qps[col] / start_max_val
            else:
                norm_scores[col] = 0

        # Clip lower bound to avoid division by zero (0.01 implies 100x slower)
        norm_scores = norm_scores.clip(lower=0.01)

        # 3. Calculate Harmonic Mean
        # HM = n / sum(1/x)
        def calc_hm(row):
            sum_reciprocal = 0.0
            for x in row:
                sum_reciprocal += 1.0 / x
            return len(row) / sum_reciprocal if sum_reciprocal > 0 else 0

        harmonic_means = norm_scores.apply(calc_hm, axis=1)

        # 4. Partition and Sort
        store_types_sorted = sorted(
            list(set(df["Store Type"])),
            key=lambda s: harmonic_means.get(s, 0),
            reverse=True,
        )

        print("Harmonic Means (Strict Balance):")
        for s in store_types_sorted:
            print(f"  {s}: {harmonic_means.get(s, 0):.4f}")
        print(f"Sorting Order (Harmonic Mean): {store_types_sorted}")

        for i, q_type in enumerate(query_types):
            ax = axes[i]
            data_subset = df[df["Query Type"] == q_type]

            # Pivot: Store x Size -> QPS
            heatmap_data = data_subset.pivot(
                index="Store Type", columns="Total Size", values="QPS"
            )
            # Reindex to ensure consistent row order across subplots
            heatmap_data = heatmap_data.reindex(store_types_sorted)

            # Create plot data: No masking, all stores participate in color scale
            plot_data = heatmap_data.copy()

            if not heatmap_data.empty:
                # Handle case where all data is masked
                if plot_data.notna().sum().sum() == 0:
                    plot_data = heatmap_data

                # Draw Heatmap without annotations first
                # Determine vmin/vmax for log scale calc
                vals = plot_data.values.flatten()
                vals = vals[~pd.isna(vals)]  # Remove NaNs
                vals = vals[vals > 0]  # Remove zeros or negatives for Log scaling

                if len(vals) > 0:
                    vmin, vmax = vals.min(), vals.max()
                else:
                    vmin, vmax = 1, 10  # dummy

                sns.heatmap(
                    plot_data,
                    annot=False,
                    cmap="YlGnBu",
                    linewidths=0.5,
                    norm=LogNorm(vmin=vmin, vmax=vmax) if len(vals) > 0 else None,
                    ax=ax,
                    cbar=False,
                )

                # Find max QPS per size considering ALL stores
                max_qps_per_col = {}
                for col in heatmap_data.columns:
                    max_qps_per_col[col] = heatmap_data[col].max()

                from math import log

                # Manual Annotation Loop
                for y, store_idx in enumerate(heatmap_data.index):
                    for x, size_col in enumerate(heatmap_data.columns):
                        val = heatmap_data.loc[store_idx, size_col]
                        if pd.isna(val):
                            continue

                        max_val = max_qps_per_col.get(size_col, val)

                        # Text Content
                        text_str = ""
                        if val > 0:
                            ratio = val / max_val
                            pct = ratio * 100
                            if ratio >= 0.99:
                                text_str = f"{val:.0f}\n(100%)"
                            else:
                                text_str = f"{val:.0f}\n({pct:.0f}%)"
                        else:
                            text_str = "0"

                        # Text Color Logic
                        # High value (dark bg) -> White, Low value (light bg) -> Black
                        text_color = "black"
                        if val > 0 and vmax > vmin:
                            try:
                                # Simple log interpolation to guess brightness
                                # YlGnBu gets dark quickly
                                log_val = log(val)
                                log_min = log(vmin)
                                log_max = log(vmax)
                                brightness = (log_val - log_min) / (log_max - log_min)
                                if brightness > 0.5:  # Darker half
                                    text_color = "white"
                            except Exception:
                                pass

                        ax.text(
                            x + 0.5,
                            y + 0.5,
                            text_str,
                            color=text_color,
                            ha="center",
                            va="center",
                            fontsize=9,
                            fontweight="normal",
                        )

            ax.set_title(q_type, fontsize=14, fontweight="bold")
            ax.set_xlabel("Dataset Size")
            if i == 0:
                ax.set_ylabel("Store Type", fontsize=12)
            else:
                ax.set_ylabel("")

        plt.suptitle(
            "Benchmark QPS Heatmap (Log Color Scale) - Higher is Better",
            fontsize=20,
            y=1.02,
        )
        plt.tight_layout()

        combined_filename = "benchmark_heatmap_combined.png"
        plt.savefig(combined_filename, bbox_inches="tight")
        print(f"  -> {combined_filename}")
        plt.close()

        # Update Markdown
        md_lines.append(f"\n![Combined Heatmap](./{combined_filename})\n")

        # Append detailed tables below
        for q_type in query_types:
            md_lines.append(f"\n### Details: {q_type}\n")
            md_lines.append(
                "\n| Store Type | Total Size | Read Size | Time (ms) | QPS | vs Best |"
            )
            md_lines.append("|---|---|---|---|---|---|")

            data_subset = df[df["Query Type"] == q_type]

            # Calculate max QPS per size group from ALL stores
            max_qps_by_size = data_subset.groupby("Total Size")["QPS"].max()

            subset_sorted = data_subset.sort_values(
                by=["Total Size", "QPS"], ascending=[True, False]
            )

            for _, row in subset_sorted.iterrows():
                size = row["Total Size"]
                qps = row["QPS"]
                store_type = row["Store Type"]

                best = max_qps_by_size.get(size, qps)
                if best > 0:
                    ratio = qps / best
                    pct = ratio * 100
                    if ratio >= 0.99:
                        factor_str = "100% (Best)"
                    else:
                        factor_str = f"{pct:.1f}%"
                else:
                    factor_str = "0%"

                md_lines.append(
                    f"| {row['Store Type']} | {row['Total Size']} | {row['Read Size']} | {row['Time (ms)']:.2f} | {row['QPS']:.2f} | {factor_str} |"
                )
            md_lines.append("\n")

    else:
        # Fallback or simple table
        md_lines.append(
            "| Store Type | Query Type | Total Size | Read Size | Time (ms) | QPS |"
        )
        md_lines.append("|---|---|---|---|---|---|")
        for r in results:
            md_lines.append(
                f"| {r['Store Type']} | {r['Query Type']} | {r['Total Size']} | {r['Read Size']} | {r['Time (ms)']:.2f} | {r['QPS']:.2f} |"
            )

        if not HAS_PLOT_DEPS:
            print("Skipping PNG generation (missing libraries).")
        elif not results:
            print("No results to plot.")

    with open("benchmark_results.md", "w") as f:
        f.writelines([line + "\n" for line in md_lines])
    print("\nUpdated benchmark_results.md")


if __name__ == "__main__":
    run_benchmark()

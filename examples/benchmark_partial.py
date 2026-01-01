from time import time
import statistics
import msgspec
import random
import string
import os
import matplotlib.pyplot as plt
from pydantic import BaseModel, ConfigDict
from msgspec import Struct


class PArtifact(BaseModel):
    id: str
    type: str
    power: int


class PUser(BaseModel):
    name: str
    artifacts: list[PArtifact]
    level: int


class PPartialUser(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    level: int


class Artifact(Struct):
    id: str
    type: str
    power: int


class User(Struct):
    name: str
    artifacts: list[Artifact]
    level: int


class PartialUser(Struct):
    name: str
    level: int


def gen_user_json(num: int) -> bytes:
    random.seed(42)
    chars = string.ascii_letters + string.digits
    artifacts = []
    for i in range(num):
        length = random.randint(200, 20000)
        r_type = "".join(random.choices(chars, k=length))
        artifacts.append(
            Artifact(
                id=f"artifact_{i}",
                type=r_type,
                power=random.randint(1, 10000),
            )
        )
    return msgspec.json.encode(
        User(
            name="Hero",
            artifacts=artifacts,
            level=10,
        )
    )


def benchmark_pydantic(d: str):
    def run():
        # Benchmark Pydantic
        start = time()
        PUser.model_validate_json(d)
        return time() - start

    return "pydantic", run


def benchmark_pydantic_partial(d: str):
    def run():
        # Benchmark Pydantic
        start = time()
        PPartialUser.model_validate_json(d)
        return time() - start

    return "pydantic+partial", run


def benchmark_msgspec(d: bytes):
    def run():
        # Benchmark Msgspec
        start = time()
        msgspec.json.decode(d, type=User)
        return time() - start

    return "msgspec+json", run


def benchmark_msgspec_partial(d: bytes):
    def run():
        # Benchmark Msgspec Partial
        start = time()
        msgspec.json.decode(d, type=PartialUser)
        return time() - start

    return "msgspec+json+partial", run


def benchmark_msgspec_msgpack(d: bytes):
    def run():
        # Benchmark Msgspec Partial
        start = time()
        msgspec.msgpack.decode(d, type=User)
        return time() - start

    return "msgspec+msgpack", run


def benchmark_msgspec_msgpack_partial(d: bytes):
    def run():
        # Benchmark Msgspec Partial
        start = time()
        msgspec.msgpack.decode(d, type=PartialUser)
        return time() - start

    return "msgspec+msgpack+partial", run


def plot_benchmark_results(results):
    plot_methods = []
    plot_times = []

    for name, median_time, count in results:
        ms_time = median_time * 1000

        # Prepare data for plot
        display_name = (
            name.replace("+", "\n+ ")
            .replace("msgspec", "msgspec ")
            .replace("pydantic", "pydantic ")
        )
        if (
            "json" not in display_name
            and "msgpack" not in display_name
            and "pydantic" in display_name
        ):
            display_name = display_name.replace("pydantic", "pydantic (json)")

        plot_methods.append(display_name)
        plot_times.append(ms_time)

    # Generate Plot
    # Reverse to have fastest at top in horizontal bar chart
    plot_methods = plot_methods[::-1]
    plot_times = plot_times[::-1]

    # Generate colors based on number of items
    colors = ["#e74c3c", "#e67e22", "#f1c40f", "#3498db", "#2ecc71", "#9b59b6"][
        : len(plot_methods)
    ]
    if len(colors) < len(plot_methods):
        colors = colors * (len(plot_methods) // len(colors) + 1)
    colors = colors[: len(plot_methods)]

    plt.figure(figsize=(10, 6))
    bars = plt.barh(plot_methods, plot_times, color=colors)

    plt.xlabel("Time (ms) - Lower is better")
    plt.title("Partial Read Benchmark Results")
    plt.grid(axis="x", linestyle="--", alpha=0.7)

    # Add value labels
    for bar in bars:
        width = bar.get_width()
        plt.text(
            width + 0.05,
            bar.get_y() + bar.get_height() / 2,
            f"{width:.4f} ms",
            va="center",
            fontweight="bold",
        )

    output_dir = "docs/source/_static"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "benchmark_plot.png")
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Plot saved to {output_path}")


def benchmark_partial():
    num = 1000
    user_json = gen_user_json(num)
    p_user_d = user_json
    m_user_d = user_json
    m_user_m = msgspec.msgpack.encode(msgspec.json.decode(user_json, type=User))

    benchmarks = [
        benchmark_msgspec(m_user_d),
        benchmark_msgspec_partial(m_user_d),
        benchmark_msgspec_msgpack(m_user_m),
        benchmark_msgspec_msgpack_partial(m_user_m),
        benchmark_pydantic(p_user_d),
        benchmark_pydantic_partial(p_user_d),
    ]
    times = {k: [] for k, _ in benchmarks}
    for _ in range(3000000):
        random.shuffle(benchmarks)
        any_bm = False
        for name, bm in benchmarks:
            if sum(times[name]) >= 1:
                continue
            duration = bm()
            times[name].append(duration)
            any_bm = True
        if not any_bm:
            break

    print("Benchmark Results (ms):")
    results = []
    for name, tlist in times.items():
        median_time = statistics.median(tlist)
        results.append((name, median_time, len(tlist)))

    results.sort(key=lambda x: x[1])
    fastest = results[0][1]

    print("| Method | Time (ms) | Factor | Runs |")
    print("| :--- | :--- | :--- | :--- |")
    for name, median_time, count in results:
        ratio = median_time / fastest
        ms_time = median_time * 1000
        print(f"| {name} | {ms_time:.4f} | {ratio:.2f}x | {count} |")

    plot_benchmark_results(results)


if __name__ == "__main__":
    benchmark_partial()

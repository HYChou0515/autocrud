"""AutoCRUD Configurable CRUD Benchmark System.

A YAML-config-driven benchmark framework for measuring AutoCRUD CRUD
operation performance across different storage backends, encodings, model
complexities, and operation types.

Usage::

    uv run python -m benchmark                          # run all scenarios
    uv run python -m benchmark --list                   # list scenarios
    uv run python -m benchmark --scenario memory-json-simple
    uv run python -m benchmark --config custom.yaml
"""

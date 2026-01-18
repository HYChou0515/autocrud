---
title: Installation Guide
description: Installation methods and dependency overview for AutoCRUD
---

# Installation Guide

## System Requirements

- Python >= 3.11
- pip or uv (recommended)

## Installation Methods

### Basic Installation

=== "Using pip"

    ```bash
    pip install autocrud
    ```

=== "Using uv"

    ```bash
    uv add autocrud
    ```

### Optional Dependencies

#### S3 Storage Support

If you need to use AWS S3 or S3-compatible object storage (such as MinIO):

=== "Using pip"

    ```bash
    pip install "autocrud[s3]"
    ```

=== "Using uv"

    ```bash
    uv add "autocrud[s3]"
    ```

#### Content-Type Auto Detection

If you need BlobStore to automatically detect file MIME types:

=== "Using pip"

    ```bash
    pip install "autocrud[magic]"
    ```

=== "Using uv"

    ```bash
    uv add "autocrud[magic]"
    ```

!!! warning "python-magic System Dependency"
    `autocrud[magic]` depends on `python-magic`, which requires `libmagic` to be installed on the system:
    
    === "Ubuntu/Debian"
        ```bash
        sudo apt-get install libmagic1
        ```
    
    === "macOS"
        ```bash
        brew install libmagic
        ```
    
    === "Windows"
        Please refer to the [python-magic installation guide](https://github.com/ahupp/python-magic#installation)

#### Full Installation

Install all optional dependencies:

=== "Using pip"

    ```bash
    pip install "autocrud[s3,magic]"
    ```

=== "Using uv"

    ```bash
    uv add "autocrud[s3,magic]"
    ```

## Verify Installation

After installation, you can verify that AutoCRUD is installed correctly:

```python
import autocrud
print(autocrud.__version__)
```

## Development Environment Setup

If you want to contribute to AutoCRUD development or run tests:

```bash
# Clone repository
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud

# Install development dependencies with uv
uv sync --all-extras

# Run tests
uv run pytest

# Build documentation
uv run mkdocs serve
```

## Next Steps

- [Quick Start](quickstart.md) - Learn how to build your first API
- [First API](first-api.md) - A detailed step-by-step guide

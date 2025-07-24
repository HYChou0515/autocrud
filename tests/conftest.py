"""pytest 配置"""

import os
import sys
import tempfile
import pytest

# 將專案根目錄加入 Python 路徑
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


@pytest.fixture
def temp_dir():
    """提供臨時目錄"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir

    # 清理
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_user_data():
    """提供示例用戶數據"""
    return {"id": "user-1", "name": "Alice", "email": "alice@example.com", "age": 30}


@pytest.fixture
def sample_product_data():
    """提供示例產品數據"""
    return {
        "id": "product-1",
        "name": "筆記本電腦",
        "description": "高性能筆記本電腦",
        "price": 25000.0,
        "category": "電子產品",
    }

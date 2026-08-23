import pytest

from models import Notice


@pytest.fixture
def sample_notice() -> Notice:
    return Notice(
        code="600519",
        name="贵州茅台",
        title="关于回购公司股份的公告",
        date="2026-07-10",
        url="https://data.eastmoney.com/notices/detail/600519/AN202607101234567890.html",
    )


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "pushed.db"

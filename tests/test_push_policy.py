import push_policy
from models import Summary


def _summary(importance):
    return Summary(importance=importance, sentiment="关注", summary="x")


def test_low_importance_not_pushed():
    assert push_policy.should_push(_summary("低"), min_importance="中") is False


def test_medium_and_high_pushed():
    assert push_policy.should_push(_summary("中"), min_importance="中") is True
    assert push_policy.should_push(_summary("高"), min_importance="中") is True


def test_unknown_importance_pushed():
    assert push_policy.should_push(_summary("未知"), min_importance="中") is True


def test_custom_high_threshold():
    assert push_policy.should_push(_summary("中"), min_importance="高") is False
    assert push_policy.should_push(_summary("高"), min_importance="高") is True


def test_per_code_override_lower(mocker):
    mocker.patch.object(push_policy.config, "WATCHLIST_THRESHOLDS", {"600519": "低"})
    # 该股低重要性也推;其他股票不受影响
    assert push_policy.should_push(_summary("低"), min_importance="中", code="600519") is True
    assert push_policy.should_push(_summary("低"), min_importance="中", code="000001") is False


def test_per_code_override_higher(mocker):
    mocker.patch.object(push_policy.config, "WATCHLIST_THRESHOLDS", {"300750": "高"})
    assert push_policy.should_push(_summary("中"), min_importance="中", code="300750") is False
    assert push_policy.should_push(_summary("高"), min_importance="中", code="300750") is True


def test_invalid_override_falls_back(mocker):
    mocker.patch.object(push_policy.config, "WATCHLIST_THRESHOLDS", {"600519": "随便"})
    # 非法覆盖值按最低门槛处理,等于放行——与全局阈值非法时行为一致
    assert push_policy.should_push(_summary("低"), min_importance="中", code="600519") is True


def test_no_code_uses_global(mocker):
    mocker.patch.object(push_policy.config, "WATCHLIST_THRESHOLDS", {"600519": "低"})
    assert push_policy.should_push(_summary("低"), min_importance="中") is False

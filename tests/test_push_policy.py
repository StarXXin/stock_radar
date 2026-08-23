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

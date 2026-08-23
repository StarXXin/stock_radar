import pytest
import requests

from exceptions import NotifyError
from notifier import PushPlusNotifier


def test_console_only_when_no_token(mocker, capsys):
    post = mocker.patch("requests.Session.post")
    PushPlusNotifier(token="").notify("标题X", "内容Y")
    post.assert_not_called()
    out = capsys.readouterr().out
    assert "标题X" in out
    assert "内容Y" in out


def test_push_success(mocker):
    resp = mocker.Mock()
    resp.json.return_value = {"code": 200}
    post = mocker.patch("requests.Session.post", return_value=resp)
    PushPlusNotifier(token="tok").notify("t", "c")
    post.assert_called_once()


def test_push_non_200_raises(mocker):
    resp = mocker.Mock()
    resp.json.return_value = {"code": 500, "msg": "err"}
    mocker.patch("requests.Session.post", return_value=resp)
    with pytest.raises(NotifyError):
        PushPlusNotifier(token="tok").notify("t", "c")


def test_push_request_exception_raises(mocker):
    mocker.patch("requests.Session.post", side_effect=requests.RequestException("boom"))
    with pytest.raises(NotifyError):
        PushPlusNotifier(token="tok").notify("t", "c")

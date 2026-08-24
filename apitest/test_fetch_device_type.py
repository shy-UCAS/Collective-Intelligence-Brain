# -*- coding: utf-8 -*-
"""设备清单抓取脚本的单元测试（不依赖真实微服务）。"""

import unittest
from unittest import mock

import requests

from fetch_device_type import (BASE_URL, PATH_ALL, PATH_GET_TYPE,
                               fetch_all_devices, fetch_device_type)


def _fake_response(payload):
    resp = mock.Mock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class FetchAllDevicesTests(unittest.TestCase):

    def test_calls_device_all_without_params(self):
        """/device/all 应不带任何参数直接请求。"""
        with mock.patch("fetch_device_type.requests.get",
                        return_value=_fake_response({"ok": True})) as get:
            fetch_all_devices()
        get.assert_called_once_with(BASE_URL + PATH_ALL, timeout=15)

    def test_returns_raw_response_json(self):
        """函数应原样返回响应 JSON，不做改写。"""
        raw = {"code": 0, "data": [{"id": "8", "deviceName": "机巢"}]}
        with mock.patch("fetch_device_type.requests.get",
                        return_value=_fake_response(raw)):
            self.assertEqual(raw, fetch_all_devices())


class FetchDeviceTypeTests(unittest.TestCase):

    def test_requests_device_type_and_sub_type_params(self):
        """deviceType 与 subType 两个必填参数应一并传递。"""
        with mock.patch("fetch_device_type.requests.get",
                        return_value=_fake_response({"ok": True})) as get:
            fetch_device_type(device_type=1, sub_type=3)
        get.assert_called_once_with(
            BASE_URL + PATH_GET_TYPE,
            params={"deviceType": 1, "subType": 3}, timeout=15)

    def test_returns_raw_response_json(self):
        """函数应原样返回响应 JSON，不做改写。"""
        raw = {"code": 0, "data": [{"id": 1, "deviceName": "摄像头1-1"}]}
        with mock.patch("fetch_device_type.requests.get",
                        return_value=_fake_response(raw)):
            self.assertEqual(raw, fetch_device_type(device_type=1, sub_type=3))


class ErrorPropagationTests(unittest.TestCase):

    def test_http_error_propagates(self):
        """HTTP 非 2xx 应抛出异常，不吞掉错误。"""
        bad = mock.Mock()
        bad.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        for fn, kwargs in ((fetch_all_devices, {}),
                           (fetch_device_type, {"device_type": 1,
                                                "sub_type": 3})):
            with mock.patch("fetch_device_type.requests.get", return_value=bad):
                with self.assertRaises(requests.HTTPError):
                    fn(**kwargs)


if __name__ == "__main__":
    unittest.main()

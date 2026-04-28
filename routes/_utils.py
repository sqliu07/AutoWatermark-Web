"""路由层共享工具函数。"""
from flask import request


def is_browser_request() -> bool:
    """判断当前请求是否来自浏览器（Accept 包含 text/html）。"""
    return "text/html" in request.headers.get("Accept", "")

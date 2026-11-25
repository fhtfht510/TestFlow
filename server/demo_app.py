"""Built-in self-contained demo app for zero-config API + UI testing."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter(prefix="/demo", tags=["demo"])

_VALID_TOKENS: dict[str, str] = {}
_ORDERS: list[dict[str, Any]] = []
_MAX_DEMO_ITEMS = 200


class LoginPayload(BaseModel):
    username: str
    password: str


class OrderPayload(BaseModel):
    item: str = "自动化测试套餐"
    amount: float = 99.0


@router.post("/api/login")
def demo_login(payload: LoginPayload) -> dict[str, Any]:
    if payload.username == "admin" and payload.password == "123456":
        token = f"demo-token-{uuid.uuid4().hex[:8]}"
        _VALID_TOKENS[token] = payload.username
        if len(_VALID_TOKENS) > _MAX_DEMO_ITEMS:
            oldest_key = next(iter(_VALID_TOKENS))
            del _VALID_TOKENS[oldest_key]
        return {"code": 0, "message": "ok", "data": {"token": token, "user": payload.username}}
    raise HTTPException(status_code=401, detail="用户名或密码错误（默认账号 admin / 123456）")


def _check_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer Token")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in _VALID_TOKENS:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    return _VALID_TOKENS[token]


@router.post("/api/orders")
def create_order(payload: OrderPayload, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _check_token(authorization)
    order_no = f"ORD-{len(_ORDERS) + 1001}-{uuid.uuid4().hex[:4].upper()}"
    order = {
        "order_no": order_no,
        "item": payload.item,
        "amount": payload.amount,
        "status": "PAID",
        "user": user,
    }
    _ORDERS.insert(0, order)
    if len(_ORDERS) > _MAX_DEMO_ITEMS:
        del _ORDERS[_MAX_DEMO_ITEMS:]
    return {"code": 0, "message": "created", "data": order}


@router.get("/api/orders")
def list_orders(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_token(authorization)
    return {"code": 0, "data": {"items": _ORDERS}}


@router.get("/page", response_class=HTMLResponse)
def demo_page() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>TestFlow 演示订单中心</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f7fb; margin: 0; padding: 32px; color: #1f2937; }
    .card { max-width: 760px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08); }
    h1 { margin-top: 0; font-size: 22px; }
    .row { display: flex; gap: 8px; margin-bottom: 16px; }
    input, button { padding: 8px 12px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 14px; }
    button { background: #2563eb; color: #fff; border: none; cursor: pointer; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #dcfce7; color: #166534; font-size: 12px; }
    .muted { color: #6b7280; font-size: 13px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>TestFlow 演示订单中心</h1>
    <p class="muted" id="status-text">正在检查登录状态...</p>
    <div class="row" id="login-box">
      <input id="username" placeholder="用户名 (admin)" value="admin" />
      <input id="password" type="password" placeholder="密码 (123456)" value="123456" />
      <button id="login-btn" onclick="login()">登录</button>
    </div>
    <div class="row">
      <button onclick="loadOrders()">刷新订单列表</button>
    </div>
    <table>
      <thead>
        <tr><th>订单号</th><th>商品</th><th>金额</th><th>状态</th></tr>
      </thead>
      <tbody id="order-body"></tbody>
    </table>
  </div>
  <script>
    async function login() {
      const username = document.getElementById("username").value;
      const password = document.getElementById("password").value;
      const res = await fetch("/demo/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      const json = await res.json();
      if (res.ok) {
        localStorage.setItem("token", json.data.token);
        await loadOrders();
      } else {
        document.getElementById("status-text").innerText = json.detail || "登录失败";
      }
    }

    async function loadOrders() {
      const token = localStorage.getItem("token");
      if (!token) {
        document.getElementById("status-text").innerText = "未登录，请先登录或通过接口注入 token";
        return;
      }
      document.getElementById("status-text").innerText = "已登录，正在加载订单...";
      const res = await fetch("/demo/api/orders", {
        headers: { "Authorization": "Bearer " + token }
      });
      const tbody = document.getElementById("order-body");
      if (!res.ok) {
        document.getElementById("status-text").innerText = "Token 无效或已过期";
        tbody.innerHTML = "";
        return;
      }
      const json = await res.json();
      const items = json.data.items || [];
      document.getElementById("status-text").innerText = `共 ${items.length} 条订单`;
      tbody.innerHTML = items.map(o =>
        `<tr><td>${o.order_no}</td><td>${o.item}</td><td>￥${o.amount}</td><td><span class="badge">${o.status}</span></td></tr>`
      ).join("");
    }

    loadOrders();
  </script>
</body>
</html>
"""

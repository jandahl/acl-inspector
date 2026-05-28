# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Lightweight HTTP routing utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class Request:
    method: str
    path: str
    query: Dict[str, List[str]]
    headers: Dict[str, str]
    body: bytes
    state: Optional[object] = None


@dataclass
class Response:
    status: int
    headers: Dict[str, str]
    body: bytes


Handler = Callable[[Request], Response]


class RouteNotFound(Exception):
    """Raised when no route matches."""


class Router:
    """Simple exact-match router."""

    def __init__(self) -> None:
        self._routes: Dict[str, Dict[str, Handler]] = {}

    def add(self, method: str, path: str, handler: Handler) -> None:
        method = method.upper()
        self._routes.setdefault(method, {})[path] = handler

    def dispatch(self, request: Request) -> Response:
        method_routes = self._routes.get(request.method.upper())
        if not method_routes:
            raise RouteNotFound(f"Method {request.method} not registered")
        handler = method_routes.get(request.path)
        if handler is None:
            raise RouteNotFound(f"No route for {request.method} {request.path}")
        return handler(request)

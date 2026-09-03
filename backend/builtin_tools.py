"""
Built-in tool implementations decorated with MAF @ai_function / @tool.

Provides:
  - web_search   : Tavily Search API
  - calculator   : Safe mathematical expression evaluation
  - weather      : Weather lookup
  - time         : Current time in specified timezone
  - fetch_url    : HTTP GET with response text extraction
"""

import asyncio
import json
import re
from datetime import datetime
from html.parser import HTMLParser
import zoneinfo

from agent_framework import tool, FunctionTool

# Alias for directive compliance
ai_function = tool


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Strip HTML tags and extract visible text."""

    SKIP_TAGS = {"script", "style", "noscript", "head", "meta", "link"}

    def __init__(self):
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.parts.append(text)


def _strip_html(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = " ".join(parser.parts)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tool Definitions with MAF @ai_function
# ---------------------------------------------------------------------------

@ai_function
async def web_search(query: str, max_results: int = 8) -> str:
    """Search the web for current information. Returns a list of results with titles, snippets, and URLs."""
    import httpx
    import os

    max_results = min(max(1, max_results), 20)
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return json.dumps({
            "query": query,
            "results": [],
            "note": "TAVILY_API_KEY not set. Add it to backend/.env to enable web search.",
        })

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return json.dumps({"query": query, "results": [], "note": f"Search failed: {e}"})

    results = [
        {
            "title": r.get("title", ""),
            "snippet": r.get("content", ""),
            "url": r.get("url", ""),
        }
        for r in data.get("results", [])
    ]

    if not results:
        return json.dumps({"query": query, "results": [], "note": "No results found."})

    return json.dumps({"query": query, "results": results})


import ast
import math
import operator

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
}

_ALLOWED_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval_ast(node):
    if isinstance(node, ast.Expression):
        return _safe_eval_ast(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
    elif isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise ValueError(f"Name '{node.id}' is not allowed")
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type in _ALLOWED_OPERATORS:
            return _ALLOWED_OPERATORS[op_type](_safe_eval_ast(node.operand))
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type in _ALLOWED_OPERATORS:
            left = _safe_eval_ast(node.left)
            right = _safe_eval_ast(node.right)
            return _ALLOWED_OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCTIONS:
            args = [_safe_eval_ast(arg) for arg in node.args]
            return _ALLOWED_FUNCTIONS[node.func.id](*args)
        raise ValueError("Unsupported function call")
    else:
        raise ValueError(f"Unsupported expression syntax: {type(node).__name__}")


@ai_function
def calculator(expression: str) -> str:
    """Safely evaluate a mathematical expression using an AST parser and return the result."""
    try:
        clean_expr = expression.strip()
        parsed = ast.parse(clean_expr, mode="eval")
        result = _safe_eval_ast(parsed)
        return json.dumps({"expression": expression, "result": str(result)})
    except Exception as e:
        return json.dumps({"expression": expression, "error": f"Calculation error: {e}"})


@ai_function
def weather(location: str) -> str:
    """Get current weather details for a given location."""
    loc_clean = location.strip()
    if not loc_clean:
        return json.dumps({"error": "Location parameter required"})
    # Mock / standard structured weather response
    return json.dumps({
        "location": loc_clean,
        "temperature": "22°C",
        "condition": "Partly Cloudy",
        "humidity": "55%",
        "wind": "12 km/h",
    })


@ai_function
def time(timezone: str = "UTC") -> str:
    """Get current time for a given IANA timezone string (default 'UTC')."""
    tz_str = timezone.strip() or "UTC"
    try:
        tz = zoneinfo.ZoneInfo(tz_str)
        now = datetime.now(tz)
        return json.dumps({"timezone": tz_str, "current_time": now.isoformat()})
    except Exception:
        now = datetime.now(zoneinfo.ZoneInfo("UTC"))
        return json.dumps({"timezone": "UTC", "current_time": now.isoformat(), "note": f"Unknown timezone '{tz_str}', fell back to UTC"})


def _rewrite_github_url(url: str) -> tuple[str, str | None]:
    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if m:
        owner, repo = m.group(1), m.group(2)
        return f"https://api.github.com/repos/{owner}/{repo}", f"https://api.github.com/repos/{owner}/{repo}/readme"

    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/blob/(.+)", url)
    if m:
        owner, repo, path = m.group(1), m.group(2), m.group(3)
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{path}", None

    return url, None


@ai_function
async def fetch_url(url: str, max_chars: int = 8000) -> str:
    """Fetch the text content of a URL."""
    max_chars = min(max(500, max_chars), 50000)

    import httpx
    import base64

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    rewritten_url, readme_url = _rewrite_github_url(url)
    is_github_repo = readme_url is not None

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers) as client:
            resp = await client.get(rewritten_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            raw = resp.text

            readme_text = ""
            if is_github_repo and readme_url:
                try:
                    readme_resp = await client.get(readme_url)
                    if readme_resp.status_code == 200:
                        readme_data = readme_resp.json()
                        encoded = readme_data.get("content", "")
                        readme_text = base64.b64decode(encoded).decode("utf-8", errors="replace")
                except Exception:
                    pass
    except Exception as e:
        return json.dumps({"error": f"Fetch failed: {e}", "url": url})

    if "html" in content_type:
        text = _strip_html(raw)
    elif "json" in content_type:
        try:
            text = json.dumps(json.loads(raw), indent=2)
        except Exception:
            text = raw
    else:
        text = raw

    combined = text + "\n\n--- README ---\n\n" + readme_text if readme_text else text
    if len(combined) > max_chars:
        combined = combined[:max_chars] + f"\n\n[truncated — {len(combined) - max_chars} more characters]"

    return json.dumps({"url": url, "content": combined})


BUILTIN_TOOLS = {
    "web_search": web_search,
    "calculator": calculator,
    "weather": weather,
    "time": time,
    "fetch_url": fetch_url,
}

BUILTIN_TOOL_NAMES = set(BUILTIN_TOOLS.keys())


def is_builtin_tool(tool_name: str) -> bool:
    return tool_name in BUILTIN_TOOL_NAMES


async def execute_builtin_tool(tool_name: str, arguments_str: str) -> str:
    """Legacy dispatcher executing builtin FunctionTool by name."""
    try:
        args = json.loads(arguments_str) if arguments_str else {}
    except json.JSONDecodeError:
        args = {}

    tool_obj = BUILTIN_TOOLS.get(tool_name)
    if not tool_obj:
        return json.dumps({"error": f"Unknown builtin tool: {tool_name}"})

    res = await tool_obj.invoke(arguments=args)
    if isinstance(res, list) and len(res) > 0 and hasattr(res[0], "text"):
        return res[0].text
    return str(res)

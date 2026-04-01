"""KrystalView MCP Server.

Gives AI agents direct access to website analytics — sessions, visitor
behavior, friction scores, anomalies, and funnel analysis.

Authenticates against the KrystalView API using the same API keys
generated in the KrystalView console.
"""

import json
import os
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("KRYSTALVIEW_API_KEY", "")
BASE_URL = os.environ.get(
    "KRYSTALVIEW_BASE_URL", "https://app.krystalview.com/api"
).rstrip("/")
TIMEOUT = int(os.environ.get("KRYSTALVIEW_TIMEOUT", "15"))

mcp = FastMCP(
    "KrystalView",
    instructions=(
        "KrystalView provides real-time website analytics with session replay, "
        "friction scoring, anomaly detection, and funnel analysis. "
        "Use these tools to investigate visitor behavior, diagnose UX issues, "
        "and answer questions about site performance."
    ),
)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY, "Accept": "application/json"}


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated GET request to the KrystalView API."""
    url = f"{BASE_URL}{path}"
    # Strip None values from params
    if params:
        params = {k: v for k, v in params.items() if v is not None}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


def _format_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return "Authentication failed. Check your KRYSTALVIEW_API_KEY."
        if status == 403:
            return "API key does not have the required 'read' scope."
        if status == 429:
            retry = exc.response.headers.get("Retry-After", "?")
            return f"Rate limited. Retry after {retry} seconds."
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        return f"API error {status}: {detail}"
    return f"Request failed: {exc}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_sessions(
    query: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    country: Optional[str] = None,
    device_type: Optional[str] = None,
    min_friction: Optional[int] = None,
    min_duration: Optional[int] = None,
    has_rage_clicks: Optional[bool] = None,
) -> str:
    """List recent visitor sessions with filtering.

    Each session includes: duration, page count, entry/exit URLs, device info,
    screen size, IP address, location (country/city), friction score, and
    rage click count.

    Use this to find sessions matching specific criteria — e.g. frustrated
    mobile users, visitors from a specific country, or high-friction sessions.

    Args:
        query: Search entry/exit URLs (e.g. "/pricing", "/checkout")
        limit: Max results (1-100, default 20)
        offset: Pagination offset
        country: Filter by country name
        device_type: "mobile" or "desktop"
        min_friction: Minimum friction score (0-10)
        min_duration: Minimum session duration in seconds
        has_rage_clicks: Only sessions with rage clicks
    """
    try:
        data = await _get("/v1/api/sessions", {
            "q": query,
            "limit": min(limit, 100),
            "offset": max(offset, 0),
            "country": country,
            "device_type": device_type,
            "min_friction": min_friction,
            "min_duration": min_duration,
            "has_rage_clicks": has_rage_clicks,
        })
        return json.dumps(data["data"], indent=2, default=str)
    except Exception as exc:
        return _format_error(exc)


@mcp.tool()
async def get_session_detail(session_id: str) -> str:
    """Get full details for a specific session.

    Returns the complete session record including: all page visits with
    timestamps, event timeline, device/browser info, IP address, geographic
    location, friction breakdown, rage clicks, errors encountered, and
    navigation path.

    Use this to deep-dive into a specific session after finding it via
    get_sessions.

    Args:
        session_id: The session primary key (UUID) from get_sessions results
    """
    try:
        data = await _get(f"/v1/api/sessions/{session_id}")
        return json.dumps(data["data"], indent=2, default=str)
    except Exception as exc:
        return _format_error(exc)


@mcp.tool()
async def get_site_stats(days: int = 7) -> str:
    """Get aggregate site statistics and performance metrics.

    Returns: total sessions, average duration, average friction score,
    bounce rate, rage click sessions, device breakdown (desktop/mobile),
    browser breakdown, top entry pages, top exit pages, daily session
    counts, and friction score distribution.

    Use this for an overview of site health and trends.

    Args:
        days: Lookback period in days (7-90, default 7)
    """
    try:
        data = await _get("/v1/api/stats", {"days": min(max(days, 7), 90)})
        return json.dumps(data["data"], indent=2, default=str)
    except Exception as exc:
        return _format_error(exc)


@mcp.tool()
async def get_anomalies(
    limit: int = 20,
    unacknowledged_only: bool = False,
) -> str:
    """Get detected anomalies for the site.

    Anomalies are automatically detected when metrics deviate significantly
    from their 7-day rolling average (>2 standard deviations). Types include:
    traffic_spike, traffic_drop, friction_surge, and bounce_spike.

    Each anomaly includes: type, severity (warning/critical), metric name,
    expected vs actual values, deviation percentage, and an AI-generated
    explanation of what likely caused it.

    Args:
        limit: Max results (1-200, default 20)
        unacknowledged_only: Only show unacknowledged anomalies
    """
    try:
        data = await _get("/v1/api/anomalies", {
            "limit": min(limit, 200),
            "unacknowledged": unacknowledged_only,
        })
        return json.dumps(data["data"], indent=2, default=str)
    except Exception as exc:
        return _format_error(exc)


@mcp.tool()
async def get_funnels() -> str:
    """List all conversion funnels defined for this site.

    Returns funnel definitions with their name, steps (URLs/patterns),
    and creation date. Use the funnel ID with get_funnel_analysis to see
    conversion rates and drop-off points.
    """
    try:
        data = await _get("/v1/api/funnels")
        return json.dumps(data["data"], indent=2, default=str)
    except Exception as exc:
        return _format_error(exc)


@mcp.tool()
async def get_funnel_analysis(funnel_id: int, days: int = 30) -> str:
    """Analyze a conversion funnel — see where users drop off.

    Returns step-by-step conversion rates showing how many sessions
    reached each step, the conversion rate between steps, and the
    overall funnel completion rate.

    Use this to identify which step in a user flow (e.g. landing ->
    signup -> checkout -> payment) loses the most visitors.

    Args:
        funnel_id: Funnel ID from get_funnels results
        days: Lookback period in days (7-90, default 30)
    """
    try:
        data = await _get(f"/v1/api/funnels/{funnel_id}/analysis", {
            "days": min(max(days, 7), 90),
        })
        return json.dumps(data["data"], indent=2, default=str)
    except Exception as exc:
        return _format_error(exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the KrystalView MCP server (stdio transport)."""
    if not API_KEY:
        import sys
        print(
            "Error: KRYSTALVIEW_API_KEY environment variable is required.\n"
            "Generate an API key in your KrystalView console under "
            "Settings > API Keys.",
            file=sys.stderr,
        )
        sys.exit(1)
    mcp.run()


if __name__ == "__main__":
    main()

import pytest

from mcp import Client

from mcp_server import mcp


@pytest.mark.anyio
async def test_mcp_lists_safe_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {tool.name for tool in tools.tools}
    assert {
        "current_time",
        "current_date",
        "open_application",
        "open_browser",
        "open_folder",
        "set_volume",
        "control_media",
        "web_search",
        "list_memories",
    } <= names
    assert "close_application" not in names
    assert "send_whatsapp_message" not in names
    assert "git_operation" not in names


@pytest.mark.anyio
async def test_mcp_validates_volume_before_execution():
    async with Client(mcp) as client:
        result = await client.call_tool("set_volume", {"level": 101})

    assert result.is_error is True


@pytest.mark.anyio
async def test_mcp_time_returns_text():
    async with Client(mcp) as client:
        result = await client.call_tool("current_time", {})

    assert result.is_error is False
    assert result.content

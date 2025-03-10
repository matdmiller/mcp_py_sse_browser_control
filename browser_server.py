import json
import httpx
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from mcp.server.fastmcp import FastMCP, Context
from web_server import WebServer

# Global state to track the web server
class ServerState:
    web_server = None
    server_started = False

state = ServerState()

@asynccontextmanager
async def mcp_lifespan(server: FastMCP) -> AsyncIterator[None]:
    # Only start the web server if it's not already running
    if not state.server_started:
        web_server = WebServer()
        web_server.start()
        state.web_server = web_server
        state.server_started = True
    else:
        print(f"Using existing web server instance")
    
    try:
        yield
    finally:
        # Stop the web server when the MCP server is shutting down
        if state.web_server:
            state.web_server.stop()
            state.server_started = False

# Create the MCP server
mcp = FastMCP("browser-js-evaluator", lifespan=mcp_lifespan)

# Function to execute JavaScript in the browser via REST API
def execute_js_in_browser(code: str) -> Dict[str, Any]:
    """Execute JavaScript in the browser and return the result synchronously"""
    try:
        response = httpx.post(
            "http://127.0.0.1:8000/execute_js",
            json={"code": code},
            timeout=5
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP error: {response.status_code}"}
    except httpx.RequestException as e:
        return {"error": f"Request error: {str(e)}"}

# MCP Tools
@mcp.tool()
async def execute_javascript(code: str, ctx: Context) -> str:
    """Execute arbitrary JavaScript code in the browser and return the result"""
    result = execute_js_in_browser(code)
    
    if "error" in result and result["error"]:
        return f"Error: {result['error']}"
    
    try:
        result_str = json.dumps(result.get('result'))
    except:
        result_str = str(result.get('result', 'No result'))
    
    return f"Result: {result_str}"

@mcp.tool()
async def add_numbers(a: float, b: float, ctx: Context) -> float:
    """Add two numbers together using JavaScript in the browser"""
    code = f"(function() {{ return {a} + {b}; }})()"
    result = execute_js_in_browser(code)
    
    if "error" in result and result["error"]:
        raise ValueError(f"Error executing JavaScript: {result['error']}")
    
    try:
        return float(result.get('result', 0))
    except (ValueError, TypeError):
        raise ValueError(f"Expected a number result, got: {result.get('result')}")

if __name__ == "__main__":
    mcp.run() 
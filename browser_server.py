import json
import httpx
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any

from mcp.server.fastmcp import FastMCP, Context
from web_server import WebServer

WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8000

# Global state to track the web server
class ServerState:
    web_server = None
    server_started = False

state = ServerState()

@asynccontextmanager
async def mcp_lifespan(server: FastMCP) -> AsyncIterator[None]:
    # Only start the web server if it's not already running
    if not state.server_started:
        web_server = WebServer(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
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
            f"http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}/execute_js",
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
    """Execute arbitrary JavaScript code in the browser and return the result.
    
    There is a web server running that hosts a page that is loaded in a browser.
    This page executes the JavaScript code you supply and returns the result.
    
    EXECUTION CONTEXT:
    Your code is automatically wrapped in an anonymous function like this:
    ```javascript
    (function() {
        // Your code goes here
        ${data.code}
    })()
    ```
    
    This means:
    1. You MUST use an explicit return statement to send results back
    2. Your return statement will be properly evaluated within this function scope
    3. All variables you declare are local to this function
    4. If you return a Promise, it will be automatically awaited
    
    The code is executed in a real browser environment with full DOM access.
    You can manipulate the page using JavaScript: read content, add elements,
    fill out forms, click buttons, etc.
    
    Examples:
        - `return document.title;` → returns the page title
        - `const links = Array.from(document.querySelectorAll('a')).map(a => a.href); return links;` → returns all links
        - `const el = document.createElement('div'); el.textContent = 'New element'; document.body.appendChild(el); return 'Element added';`
    
    IMPORTANT:
    - DO NOT just use console.log() for results - they won't be returned to you
    - Results are serialized to JSON when possible, or converted to string
    - If your code returns a Promise, it will be automatically awaited
    
    Do not do anything evil or malicious with this tool.
    """
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
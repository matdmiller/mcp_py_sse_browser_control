# Browser JavaScript Evaluator

This project provides a way to execute JavaScript code in a browser from Python using MCP (Model Control Protocol).

# <span style="color: red;">⚠️ WARNING ⚠️</span>

**This MCP server can execute arbitrary JavaScript in your browser. This can be dangerous. Be aware of the implications of this before using this plugin. Use at your own risk.**


## Architecture

The project is split into two main components:

1. **Web Server (`web_server.py`)**: 
   - Handles browser connections via Server-Sent Events (SSE)
   - Provides a REST API endpoint for executing JavaScript
   - Returns results synchronously

2. **MCP Server (`mcp_server.py`)**: 
   - Manages the lifecycle of the web server
   - Provides MCP tools for executing JavaScript
   - Communicates with the web server via REST API calls

## How It Works

1. The MCP server starts the web server during its lifecycle initialization
2. A browser connects to the web server via SSE
3. When an MCP tool is called, it makes a REST API call to the web server
4. The web server sends the JavaScript code to the browser via SSE
5. The browser executes the code and sends the result back to the web server
6. The web server returns the result to the MCP server
7. The MCP server returns the result to the caller

## Usage

### Add the MCP server to your Claude config

```json
  ...
  "browser-js-evaluator": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/this/repo/mcp_py_sse_browser_control",
        "run",
        "browser_server.py"
      ]
    }
  }
  ...
```

When you launch Claude Desktop this will start both the MCP server and the web server. Then open a browser and navigate to http://127.0.0.1:8000 to connect to the web server.

### Using the MCP Tools

The MCP server provides two tools:

1. `execute_javascript`: Execute arbitrary JavaScript code in the browser
2. `add_numbers`: Add two numbers together using JavaScript in the browser

These tools can be called from any MCP client.

## Development

To run the web server independently (for testing):

```bash
python web_server.py
```

This will start only the web server without the MCP integration.
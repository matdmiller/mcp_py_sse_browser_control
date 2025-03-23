import asyncio
import json
import threading
import time
import uuid
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import uvicorn

# Global state
class ServerState:
    sse_clients = {}
    js_results = {}

state = ServerState()

# HTML content for the web page
HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <title>Browser JS Evaluator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .status {
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
        }
        .connected {
            background-color: #d4edda;
            color: #155724;
        }
        .disconnected {
            background-color: #f8d7da;
            color: #721c24;
        }
        .log {
            height: 300px;
            overflow-y: auto;
            background-color: #f8f9fa;
            padding: 10px;
            border: 1px solid #dee2e6;
            border-radius: 5px;
        }
        .heartbeat {
            font-size: 0.8em;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <h1>Browser JS Evaluator</h1>
    
    <div id="status" class="status disconnected">
        Status: Disconnected
    </div>
    
    <div id="heartbeat" class="heartbeat">
        Last heartbeat: Never
    </div>
    
    <h2>Console Output</h2>
    <div id="log" class="log"></div>
    
    <script>
        const statusEl = document.getElementById('status');
        const heartbeatEl = document.getElementById('heartbeat');
        const logEl = document.getElementById('log');
        let eventSource;
        let clientId = null;
        
        // Override console.log to capture output
        const originalConsoleLog = console.log;
        console.log = function() {
            const args = Array.from(arguments);
            originalConsoleLog.apply(console, args);
            
            const logEntry = document.createElement('div');
            logEntry.textContent = args.map(arg => 
                typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
            ).join(' ');
            logEl.appendChild(logEntry);
            logEl.scrollTop = logEl.scrollHeight;
        };
        
        // Function to connect to SSE
        function connectSSE() {
            clientId = Math.random().toString(36).substring(2, 15);
            eventSource = new EventSource(`/sse/${clientId}`);
            
            eventSource.onopen = function() {
                statusEl.textContent = 'Status: Connected';
                statusEl.className = 'status connected';
                console.log('SSE connection established');
            };
            
            eventSource.onerror = function() {
                statusEl.textContent = 'Status: Disconnected';
                statusEl.className = 'status disconnected';
                console.log('SSE connection error, trying to reconnect...');
                eventSource.close();
                setTimeout(connectSSE, 1000);
            };
            
            eventSource.addEventListener('heartbeat', function(event) {
                heartbeatEl.textContent = 'Last heartbeat: ' + new Date().toLocaleTimeString();
            });
            
            eventSource.addEventListener('execute_js', async function(event) {
                const data = JSON.parse(event.data);
                console.log('Executing JavaScript:', data.code);
                
                try {
                    // Wrap the code in an anonymous function and execute it immediately
                    let result = (new Function(`
                        return (async function() {
                            try {
                                const result = (async () => { ${data.code} })();
                                return await result;
                            } catch (e) {
                                throw e;
                            }
                        })();
                    `))();
                    
                    result = await result;
                    
                    fetch('/js_result', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            execution_id: data.execution_id,
                            result: result,
                            error: null
                        })
                    });
                } catch (error) {
                    fetch('/js_result', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            execution_id: data.execution_id,
                            result: null,
                            error: error.toString()
                        })
                    });
                }
            });
        }
        
        // Connect to SSE when page loads
        connectSSE();
        
        // Reconnect if the connection is lost
        window.addEventListener('beforeunload', function() {
            if (eventSource) {
                eventSource.close();
            }
        });
    </script>
</body>
</html>
"""

# Create the FastAPI application
def create_web_app():
    app = FastAPI()
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/", response_class=HTMLResponse)
    async def get_html():
        return HTMLResponse(content=HTML_CONTENT)
    
    @app.get("/sse/{client_id}")
    async def sse(client_id: str):
        async def event_generator():
            # Register this client
            queue = asyncio.Queue()
            state.sse_clients[client_id] = queue
            print(f"SSE client registered: {client_id}, total clients: {len(state.sse_clients)}")
            
            try:
                # Send initial heartbeat
                yield {
                    "event": "heartbeat",
                    "data": json.dumps({"time": time.time()})
                }
                
                # Send heartbeats and handle messages
                while True:
                    try:
                        data = await asyncio.wait_for(queue.get(), timeout=5)
                        yield data
                    except asyncio.TimeoutError:
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps({"time": time.time()})
                        }
            except asyncio.CancelledError:
                print(f"SSE client disconnected: {client_id}")
            finally:
                # Make sure to remove client even if there was an error
                if client_id in state.sse_clients:
                    del state.sse_clients[client_id]
                    print(f"Removed client {client_id}, remaining clients: {len(state.sse_clients)}")
        
        return EventSourceResponse(event_generator())
    
    @app.post("/js_result")
    async def js_result(request: Request):
        data = await request.json()
        execution_id = data.get("execution_id")
        if execution_id:
            state.js_results[execution_id] = data
        return JSONResponse({"status": "ok"})
    
    # New synchronous endpoint for executing JavaScript
    @app.post("/execute_js")
    async def execute_js(request: Request):
        data = await request.json()
        code = data.get("code")
        execution_id = str(uuid.uuid4())
        
        if not state.sse_clients:
            return JSONResponse({"error": "No browser clients connected"})
        
        client_id = next(iter(state.sse_clients))
        queue = state.sse_clients[client_id]
        
        # Create a new event loop for this request
        loop = asyncio.get_event_loop()
        
        async def execute():
            await queue.put({
                "event": "execute_js",
                "data": json.dumps({
                    "execution_id": execution_id,
                    "code": code
                })
            })
            
            # Wait for the result (with timeout)
            for _ in range(30):  # 3 seconds timeout
                if execution_id in state.js_results:
                    return state.js_results.pop(execution_id)
                await asyncio.sleep(0.1)
            
            return {"error": "Execution timed out"}
        
        result = await execute()
        return JSONResponse(result)
    
    return app

# Web server class
class WebServer:
    def __init__(self, host="127.0.0.1", port=8000):
        self.host = host
        self.port = port
        self.app = create_web_app()
        self.should_exit = threading.Event()
        self.thread = None
    
    def run_server(self):
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        server = uvicorn.Server(config)
        server.run()
    
    def start(self):
        self.thread = threading.Thread(target=self.run_server, daemon=True)
        self.thread.start()
        print(f"Web server started at http://{self.host}:{self.port}")
    
    def stop(self):
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
            print("Web server stopped")

if __name__ == "__main__":
    server = WebServer()
    server.start()
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop() 
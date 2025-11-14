# ABC

This project is a multi-module project, and each agent has its own independent execution environment.
Therefore, when running the project, you need to execute the following command inside each agent’s folder.

1. workspace-console-manager
<!-- adk web -->
a. uv run adk web . --port 8501 --reload_agents
<!-- agent-server -->
b. uv run uvicorn app.server:app --host localhost --port 8000 --reload

2. user-agent
<!-- agent-server -->
uv run uvicorn app.fast_api_app:app --host localhost --port 8001 --reload

3. mail-agent
<!-- agent-server -->
uv run uvicorn app.fast_api_app:app --host localhost --port 8002 --reload



# LeanBridge Project

LeanBridge is a multi-agent Lean 4 proof assistant. The project adopts a decoupled frontend-backend architecture, with the backend based on the OpenAI Agents SDK and the frontend based on the AG-UI protocol and React.

## Project Structure

```text
LeanBridge/
├── client/              # [TBD] React-based web frontend
└── server/              # [Core] Python backend project (Agents, API, Lean interaction)
    ├── agent/           # Agent logic (Plan, Code, Search, Verify)
    ├── cli.py           # Interactive Command Line Interface (CLI) entry point
    ├── app.py           # FastAPI Web Service entry point
    ├── env_setup.py     # Environment initialization and path management
    ├── config.py        # Configuration loading and management
    ├── config.yaml      # Configuration file (model selection, parameters, etc.)
    ├── .env             # Environment variables (API Keys, sensitive info)
    └── requirements.txt # Backend dependencies (including customized SDK)
```

## Quick Start (Backend)

1.  **Install Environment**:
    Ensure Python 3.10+ is installed. This project depends on a customized version of the OpenAI Agents SDK.
    ```bash
    cd server
    pip install -r requirements.txt
    ```

2.  **Configure System**:
    *   **Environment Variables**: Create a `.env` file based on `.env.example`, and fill in the model API Key and Base URL.
    *   **YAML Configuration**: Create a `config.yaml` file based on `config.yaml.example`, and adjust the agent model settings.

3.  **Run the Application**:

    *   **Option A: Start Interactive CLI (Recommended for Dev/Test)**
        ```bash
        cd server
        python cli.py
        ```
        Enter the command-line interface to interact directly with the Plan Agent.

    *   **Option B: Start Web API Service**
        ```bash
        cd server
        python app.py
        ```
        The service runs on `http://localhost:8000` by default and can be used with the frontend.

## Tech Stack

- **LLM SDK**: [sciencraft/openai-agents-python](https://github.com/sciencraft/openai-agents-python.git) (Customized Version)
- **Web Framework**: FastAPI & AG-UI
- **Agent Framework**: Wrapped based on OpenAI Agents SDK
- **Verification**: FastMCP & Lean 4

## Frontend (Client)

* The frontend project is currently reserved and will be updated in the future.

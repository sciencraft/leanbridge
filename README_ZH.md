# LeanBridge Project

LeanBridge 是一个多智能体Lean 4 证明助手。项目采用了前后端分离的结构，后端基于 OpenAI Agents SDK，前端基于AG-UI协议和React。

## 项目结构

```text
LeanBridge/
├── client/              # [待更新] 基于 React 的网页前端
└── server/              # [核心] Python 后端项目 (Agent, API, Lean 交互)
    ├── agent/           # Agent 逻辑 (Plan, Code, Search, Verify)
    ├── cli.py           # 交互式命令行 (CLI) 入口
    ├── app.py           # FastAPI Web 服务入口
    ├── env_setup.py     # 环境初始化与路径管理
    ├── config.py        # 配置加载与管理
    ├── config.yaml      # 配置文件 (模型选择、参数等)
    ├── .env             # 环境变量 (API Keys, 敏感信息)
    └── requirements.txt # 后端依赖 (包含定制版 SDK)
```

## 快速开始 (后端)

1.  **安装环境**:
    确保已安装 Python 3.10+。本项目依赖一个定制版的 OpenAI Agents SDK。
    ```bash
    cd server
    pip install -r requirements.txt
    ```

2.  **配置系统**:
    *   **环境变量**: 参考 `.env.example` 创建 `.env` 文件，填入模型 API Key 和 Base URL。
    *   **YAML 配置**: 参考 `config.yaml.example` 创建 `config.yaml`，调整智能体模型设置。

3.  **运行方式**:

    *   **方式 A：启动交互式 CLI (推荐开发测试)**
        ```bash
        cd server
        python cli.py
        ```
        进入命令行交互界面，直接与 Plan Agent 交流。

    *   **方式 B：启动 Web API 服务**
        ```bash
        cd server
        python app.py
        ```
        服务默认运行在 `http://localhost:8000`，可配合前端使用。

## 技术栈

- **LLM SDK**: [sciencraft/openai-agents-python](https://github.com/sciencraft/openai-agents-python.git) (定制版)
- **Web Framework**: FastAPI & AG-UI
- **Agent Framework**: 基于 OpenAI Agents SDK 封装
- **Verification**: FastMCP & Lean 4

## 前端 (Client)

* 前端项目目前预留，待后续更新。
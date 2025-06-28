# mcp-mysql

## 🤓 MCP 概况

“MCP 宛如一个万能适配器，使 AI 模型得以运用统一标准对接任意系统。它并未针对各数据源构建专属连接，反倒提供了一个通用的即插即用接口，任何 AI 模型皆可借此获取信息或执行任务。”

MCP 是一个开放协议，它为应用程序向 LLM 提供上下文的方式进行了标准化。你可以将 MCP 想象成 AI 应用程序的 USB-C 接口。就像 USB-C 为设备连接各种外设和配件提供了标准化的方式一样，MCP 为 AI 模型连接各种数据源和工具提供了标准化的接口。

具体来说，MCP Server 就是运行在*本地的 node.js 或 python 程序*
大模型通过 stdio（标准输入输出）调用某个 MCP Server，然后 MCP 通过自身代码功能访问外部工具完成请求。


## 🧱 项目架构
- `main.py` : MCP Server 定义程序，调用此程序来连接数据库，执行SQL
- `test.py` : 项目入口程序，使用此程序调用 LLM , MCP 等工具
- `mcp-mysql.log` : MCP 查询日志文件
- `requirements.txt` : 存有项目依赖库信息的静态文件

## 🔧 主要功能

- **LLM API 调用**： 输入自然语言 → LLM 输出 SQL
- **查询控制**：获取 schema，执行 SQL，解析并返回 JSON 结果
- **CLI 界面实现**：可在终端交互输入自然语言并返回查询结果
- **查询日志记录**：记录每次执行的 SQL 和时间戳 并 输出到本地文件（`log.txt`）
- **查询结果分页**：长查询结果支持用户在 CLI 输入 next 逐页返回
- **只读 SQL 白名单过滤**：MCP 内部解析 SQL，仅允许 SELECT 语句
- **关键字段访问控制**：禁止查询包含 password、salary 等字段
- **Prompt 模板优化**：使用高级 Prompt ，提高生成 SQL 的准确率


## 📄 部署方式
本项目推荐使用 Python 虚拟环境进行部署，以管理项目依赖。

1.  **克隆仓库**：
    ```bash
    git clone https://github.com/RaShiSho/mcp-mysql.git
    cd mcp-mysql
    ```

2.  **创建并激活虚拟环境**：
    ```bash
    uv venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

3.  **安装依赖**：

	```bash
    uv pip install -r requirements.txt
    ```

4. **环境变量设置**

    MCP会通过以下环境变量访问数据库
    - `DB-HOST`：数据库系统地址
    - `DB-USER`：数据库系统用户名
    - `DB-PASSWORD`：用户密码
    - `DB-NAME`：处理的数据库名字
    - `DB-PORT`：数据库端口

    你可以在你的电脑上设置对应环境变量，然后让项目访问
    也可以直接修改 `main.py` 里 `DB_CONFIG` 中的内容，将 `os.getenv()` 第二个参数（默认值）改为你希望的值


## 🕹️ 运行项目

在完成部署后，就可以选择以下命令运行项目

1. 若已进入uv虚拟环境，直接执行
    ```bash
    python test.py
    ```
2. 若没有进入虚拟环境，可以使用 `uv run` 快速执行
    ```bash
    uv run test.py
    ```


## 🫡 参考项目

[Simple MCP MySQL Server](https://github.com/alexcc4/mcp-mysql-server)


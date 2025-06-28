import asyncio
import textwrap
import os
import json
import httpx
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# --- 1. 配置: 指向你的MCP服务脚本 ---
server_params = StdioServerParameters(
    command="python",
    args=["main.py"],
    env=None,
)

# --- 2. 配置: 通义千问 API ---
# 建议使用环境变量 TONGYI_API_KEY 存储你的 API Key，更加安全
# Windows: set TONGYI_API_KEY=your_api_key
# macOS/Linux: export TONGYI_API_KEY=your_api_key
TONGYI_API_KEY = os.getenv("DASHSCOPE_API_KEY")
# 使用通义千问最新的 v2 版本 API 地址
TONGYI_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
# 使用 qwen-turbo 模型，性价比高
MODEL_NAME = "qwen-turbo"


def print_header(title, char="="):
    """打印一个漂亮的标题头"""
    print("\n" + char * 60)
    print(f" {title}")
    print(char * 60)

def pretty_print_json(data):
    """美化打印 JSON 对象"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# --- 3. 新增: 通义 API 调用模块 ---
async def generate_sql_with_llm(user_query: str, schema_json: dict) -> str:
    """
    使用通义大模型将自然语言转换为 SQL 查询。

    Args:
        user_query: 用户输入的自然语言问题。
        schema_json: 数据库的 schema 信息，用于构建 prompt。

    Returns:
        由模型生成的 SQL 查询字符串，如果失败则返回 None。
    """
    print("\n> [LLM] 正在构造 Prompt 并请求大模型生成 SQL...")

    # 从 schema 信息中提取表结构，用于注入 Prompt
    schema_description = json.dumps(schema_json.get("tables", {}), indent=2)

    # 构造高质量的 Prompt
    prompt = textwrap.dedent(f"""
    你是一个顶级的数据库专家，擅长将用户的自然语言问题转换成 SQL 查询语句。
    请根据下面提供的数据库表结构信息，将用户的问题转换成一个有效的、只读的 SELECT 查询。

    **数据库表结构信息:**
    ```json
    {schema_description}
    ```

    **约束:**
    1.  你只能生成 `SELECT` 语句。
    2.  确保查询的表名和字段名与上述结构信息中的完全一致。
    3.  最终的输出结果中，只能包含 SQL 语句，不要包含任何额外的解释、注释或格式化（如 ```sql ... ```）。
    4.  你被禁止查询包含 password、salary 等字段

    **用户问题:**
    "{user_query}"

    **SQL 查询:**
    """).strip()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TONGYI_API_KEY}",
    }

    payload = {
        "model": MODEL_NAME,
        "input": {
            "prompt": prompt
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(TONGYI_API_URL, headers=headers, json=payload)

        if response.status_code == 200:
            response_data = response.json()
            generated_sql = response_data.get("output", {}).get("text", "").strip()
            
            # 移除模型可能返回的代码块标记
            if generated_sql.lower().startswith("```sql"):
                generated_sql = generated_sql[5:].strip()
            if generated_sql.endswith("```"):
                generated_sql = generated_sql[:-3].strip()

            if generated_sql:
                print(f"> [LLM] SQL 生成成功: {generated_sql}")
                return generated_sql
            else:
                print("> [LLM] 错误: 模型返回了空内容。")
                pretty_print_json(response_data)
                return None
        else:
            print(f"> [LLM] 错误: API 请求失败，状态码: {response.status_code}")
            print(f"> [LLM] 响应内容: {response.text}")
            return None
    except httpx.RequestError as e:
        print(f"> [LLM] 错误: 网络请求异常 - {e}")
        return None
    except Exception as e:
        print(f"> [LLM] 错误: 解析 LLM 响应时发生未知错误 - {e}")
        return None



# --- 4. 修改: 主程序逻辑，实现查询控制与 CLI 界面 ---
async def interactive_cli():
    """
    启动一个交互式 CLI，连接到 MCP 服务，
    将用户的自然语言输入转换为 SQL 并执行。
    """
    if not TONGYI_API_KEY or "YOUR_TONGYI_API_KEY_HERE" in TONGYI_API_KEY:
        print_header("配置错误", "!")
        print("错误: 通义 API Key 未设置。")
        print("请通过设置环境变量 TONGYI_API_KEY 来提供你的 Key。")
        print("例如 (Linux/macOS): export TONGYI_API_KEY='sk-xxxxxxxx'")
        print("或直接在脚本中修改 TONGYI_API_KEY 变量。")
        return

    # 分页相关逻辑变量
    page_size = 5
    last_results = []
    current_page = 0


    print("正在启动 MCP 客户端并连接到服务...")
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ MCP 服务连接成功!")

                # resources = await session.list_resources()
                # print("Available Resources:")
                # print(f"   {resources}")
                
                # tools = await session.list_tools()
                # print("Available Tools:")
                # print(f"   {tools}")

                # 启动时预先获取一次 schema
                print("> [MCP] 正在获取数据库 Schema...")
                content_bytes, _ = await session.read_resource("mysql://schema")
                text_resource = _[1][0]  # 提取 TextResourceContents 对象
                decoded = text_resource.text           # 直接拿到 JSON 字符串
                schema_info = json.loads(decoded)      # 转成 dict

                # try:
                #     decoded = content_bytes.decode('utf-8')
                #     print(f"[调试] MCP返回原始内容：{decoded}")
                #     schema_info = json.loads(decoded)
                # except Exception as e:
                #     print(f"[错误] schema 解析失败: {e}")
                #     return
                print("> [MCP] Schema 获取成功.")

                print_header("自然语言数据库查询 CLI", "*")
                print("你好！你可以用自然语言向我提问数据库相关的问题。")
                print("例如: '查询所有职员' 或 '学分最高的学生是谁？'")
                print("输入 'exit' 或 'quit' 即可退出程序。")

                while True:
                    print("-" * 60)
                    user_input = input("请输入你的问题（或指令） > ")

                    if user_input.lower() in ["exit", "quit"]:
                        print("再见！")
                        break
                    

                    # 分页命令：
                    if user_input.lower() == "next":
                        if not last_results:
                            print("没有可分页的结果，请先执行查询。")
                            continue
                        start = current_page * page_size
                        end = start + page_size
                        page = last_results[start:end]
                        if page:
                            print_header(f"第 {current_page + 1} 页结果", "-")
                            pretty_print_json(page)
                            current_page += 1
                        else:
                            print("已经是最后一页了。")
                        continue



                    # 1. 自然语言 -> SQL (通过 LLM)
                    sql_query = await generate_sql_with_llm(user_input, schema_info)

                    if not sql_query:
                        print("\n无法执行查询，因为未能成功生成 SQL。请尝试换个问法。")
                        continue
                    

                    # 2. 执行 SQL (通过 MCP Tool)
                    print(f"> [MCP] 正在使用工具 'query_data' 执行 SQL...")
                    tool_result = await session.call_tool("query_data", {"sql": sql_query})


                    # 3. 解析并返回 JSON 结果
                    print("> [MCP] 收到查询结果:")
                    structured = getattr(tool_result, "structuredContent", None)

                    result_data = structured.get("result", {})

                    if result_data.get("success"):
                        last_results = result_data.get("results", [])
                        current_page = 0
                        total = len(last_results)
                        print(f"> 查询总记录数：{total}，每页 {page_size} 条，可使用 'next' 查看后续。")

                        # 显示第一页
                        page = last_results[:page_size]
                        print_header(f"第 1 页结果", "-")
                        pretty_print_json(page)
                        current_page += 1
                    else:
                        print_header("查询失败", "!")
                        print('\n' + result_data.get("error") + '\n')


    except Exception as e:
        print(f"\n程序发生意外错误: {e}")
    finally:
        print("\nCLI 会话已结束。")


# --- 程序入口 ---
if __name__ == "__main__":
    asyncio.run(interactive_cli())
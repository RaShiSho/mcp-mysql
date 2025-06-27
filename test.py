import asyncio
import textwrap
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# --- 配置: 指向你的MCP服务脚本 ---
server_params = StdioServerParameters(
    command="python",
    args=["main.py"],
    env=None,
)

def print_header(title):
    """打印一个漂亮的标题头"""
    print("\n" + "=" * 60)
    print(f"▶️  TESTING: {title}")
    print("=" * 60)


async def run_tests():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("\nConnection Initialized Successfully!")
            print_header("Directly Reading Resource Content")
            
            resources = await session.list_resources()
            print("Available Resources:")
            print(f"   {resources}")
            
            tools = await session.list_tools()
            print("Available Tools:")
            print(f"   {tools}")

            # 测试 file:// 资源
            content, mime_type = await session.read_resource("mysql://tables")
            print(mime_type)

            # 测试 mysql://schema 资源
            print("\n✅ Requesting 'mysql://schema'...")
            content, mime_type = await session.read_resource("mysql://schema")
            print(mime_type)


            print_header("Directly Calling Tool: query_data (Multiple Cases)")

            # Case 1: 成功的简单查询
            print("\n✅ Case 1 (Success - users):")
            result1 = await session.call_tool("query_data", {"sql": "SELECT * FROM users"})
            print("   Raw Response Object:")
            print(f"   {result1}")

# --- 程序入口 ---
if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except FileNotFoundError:
        print("\n" + "=" * 60)
        print(f"ERROR: Could not find the server script '{server_params.args[0]}'.")
        print("Please make sure this test script is in the same directory as your MCP server script.")
        print("=" * 60)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        print("\n Raw print test suite finished.")

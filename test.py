import asyncio
import textwrap
import json
import re
import os
import openai
from typing import Dict, Any, Optional, Tuple, List
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# --- 配置: 指向你的MCP服务脚本 ---
server_params = StdioServerParameters(
    command="python",
    args=["main.py"],
    env=None,
)

# --- 辅助函数：解析资源内容 ---
def extract_resource_content(resource_contents: Tuple[str, List[types.TextResourceContents]]) -> Dict[str, Any]:
    """
    从资源内容元组中提取实际内容
    """
    if resource_contents[0] == 'contents' and resource_contents[1]:
        # 获取第一个文本资源内容
        text_content = resource_contents[1][0].text
        try:
            return json.loads(text_content)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON content", "raw": text_content}
    return {"error": "No content found"}

# --- 自然语言转SQL模块 ---
class NLtoSQLConverter:
    """
    自然语言转SQL转换器，使用DASHSCOPE API
    功能：将自然语言问题转换为可执行的SQL语句
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-plus"):
        """
        初始化转换器
        
        :param api_key: DASHSCOPE API密钥（如果未提供则从环境变量读取）
        :param model: 使用的DASHSCOPE AI模型名称
        """
        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided and DASHSCOPE_API_KEY environment variable not set")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.schema_cache = {}  # 用于缓存不同数据库的schema
    
    async def get_schema(self, session: ClientSession, db_identifier: str) -> Dict[str, Any]:
        """
        获取数据库schema并缓存结果
        
        :param session: MCP客户端会话
        :param db_identifier: 数据库标识符 (e.g., "mysql://schema")
        :return: 数据库schema字典
        """
        if db_identifier not in self.schema_cache:
            # 根据main.py的实现，schema资源返回字典结构
            resource_contents, _ = await session.read_resource(db_identifier)
            schema_data = extract_resource_content(resource_contents)
            self.schema_cache[db_identifier] = schema_data
        return self.schema_cache[db_identifier]
    
    async def generate_sql(self, 
                          session: ClientSession, 
                          nl_query: str, 
                          db_identifier: str = "mysql://schema") -> Dict[str, Any]:
        """
        生成SQL查询语句
        
        :param session: MCP客户端会话
        :param nl_query: 自然语言查询
        :param db_identifier: 数据库schema资源标识符
        :return: 包含SQL和元数据的字典
        """
        try:
            # 获取数据库schema字典
            schema_data = await self.get_schema(session, db_identifier)
            
            # 检查schema数据是否有效
            if "error" in schema_data:
                return {
                    "error": f"Schema error: {schema_data.get('error')}",
                    "sql": "",
                    "confidence": 0
                }
            
            # 将schema字典转换为字符串表示
            schema_str = self._format_schema(schema_data)
            
            # 构建LLM提示
            prompt = self._build_prompt(nl_query, schema_str)
            
            # 调用OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=256,
                response_format={"type": "json_object"}
            )
            
            # 解析响应
            return self._parse_response(response.choices[0].message.content)
        except Exception as e:
            return {
                "error": f"Generation failed: {str(e)}",
                "sql": "",
                "confidence": 0
            }
    
    def _format_schema(self, schema_data: Dict[str, Any]) -> str:
        """将schema字典格式化为字符串表示"""
        # 检查schema数据结构
        if not isinstance(schema_data, dict) or "tables" not in schema_data:
            return f"Invalid schema format: {json.dumps(schema_data)}"
        
        db_name = schema_data.get("database", "unknown_database")
        tables = schema_data.get("tables", {})
        
        schema_str = f"Database: {db_name}\n\n"
        
        for table_name, columns in tables.items():
            schema_str += f"Table: {table_name}\n"
            for col in columns:
                col_info = f"  {col['name']}: {col['type']}"
                # 添加约束信息
                constraints = []
                if col.get('key') == 'PRI':
                    constraints.append('PRIMARY KEY')
                if col.get('null') == 'NO':
                    constraints.append('NOT NULL')
                if col.get('default') is not None:
                    constraints.append(f"DEFAULT {col['default']}")
                if col.get('extra'):
                    constraints.append(col['extra'])
                
                if constraints:
                    col_info += f" [{', '.join(constraints)}]"
                
                schema_str += col_info + "\n"
            schema_str += "\n"
        
        return schema_str.strip()
    
    def _build_prompt(self, nl_query: str, schema: str) -> str:
        """构建LLM提示"""
        return f"""
        ## 任务
        将自然语言问题转换为精确的SQL查询语句。数据库是MySQL。
        
        ## 数据库Schema
        {schema}
        
        ## 用户问题
        "{nl_query}"
        
        ## 输出要求
        1. 只生成SQL语句，不要包含任何解释或额外文本
        2. 确保SQL语法完全正确
        3. 使用JSON格式返回结果：
        {{
            "sql": "生成的SQL语句",
            "confidence": "对生成结果的置信度评分(0-100)",
            "tables_used": ["查询涉及的表名"]
        }}
        
        ## 关键注意事项
        - 使用反引号(`)引用表名和列名，而非双引号
        - 确保所有引号都是闭合的
        - 如果问题无法转换为SQL，设置"sql"为空字符串并添加"error"字段说明原因
        - 特别注意WHERE子句的准确性
        - 日期函数使用CURDATE()获取当前日期
        - 仅支持单表查询（不允许使用JOIN）
        
        ## 示例
        用户问题: "显示最近的10个订单"
        正确SQL: SELECT * FROM `orders` ORDER BY `order_date` DESC LIMIT 10;
        """
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应并清理SQL语句"""
        try:
            result = json.loads(response)
            
            # 清理SQL语句
            if 'sql' in result:
                result['sql'] = self._clean_sql(result['sql'])
                
            # 检查空SQL情况
            if result.get('sql', '').strip() in ('', ';'):
                result['error'] = result.get('error', 'Generated SQL is empty')
                
            return result
        except json.JSONDecodeError:
            return {
                "error": "Invalid JSON response", 
                "raw_response": response,
                "sql": "",
                "confidence": 0
            }
    
    def _clean_sql(self, sql: str) -> str:
        """清理SQL语句中的常见问题"""
        # 移除SQL代码块标记
        sql = re.sub(r'```sql|```', '', sql, flags=re.IGNORECASE)
        # 移除开头/结尾引号
        sql = re.sub(r'^["\']+|["\']+$', '', sql.strip())
        # 确保以分号结尾
        if not sql.endswith(';'):
            sql += ';'
        return sql.strip()

# --- 测试辅助函数 ---
def print_header(title):
    """打印一个漂亮的标题头"""
    print("\n" + "=" * 60)
    print(f"▶️  TESTING: {title}")
    print("=" * 60)

# --- 主测试函数 ---
async def run_tests():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("\nConnection Initialized Successfully!")
            
            # 创建NL转SQL转换器
            sql_generator = NLtoSQLConverter()
            
            # 测试资源访问
            print_header("Resource Access Tests")
            
            resources = await session.list_resources()
            print("Available Resources:")
            # 提取资源名称列表
            resource_list = resources[2] if len(resources) > 2 else []
            for res in resource_list:
                print(f"   - {res.name}: {res.uri}")
            
            tools = await session.list_tools()
            print("\nAvailable Tools:")
            # 提取工具名称列表
            tool_list = tools[2] if len(tools) > 2 else []
            for tool in tool_list:
                print(f"   - {tool.name}: {tool.description}")
            
            # 测试 schema 资源
            print("\n✅ Requesting 'mysql://schema'...")
            resource_contents, mime_type = await session.read_resource("mysql://schema")
            print(f"   MIME Type: {mime_type}")
            
            # 提取实际内容
            schema_data = extract_resource_content(resource_contents)
            print(f"   Database: {schema_data.get('database', 'N/A')}")
            if "tables" in schema_data:
                print(f"   Tables: {', '.join(schema_data['tables'].keys())}")
            
            # 测试 tables 资源
            print("\n✅ Requesting 'mysql://tables'...")
            resource_contents, mime_type = await session.read_resource("mysql://tables")
            print(f"   MIME Type: {mime_type}")
            
            # 提取实际内容
            tables_data = extract_resource_content(resource_contents)
            print(f"   Database: {tables_data.get('database', 'N/A')}")
            if "tables" in tables_data:
                print(f"   Tables: {', '.join(tables_data['tables'])}")
            
            # 自然语言转SQL测试
            print_header("Natural Language to SQL Conversion")
            
            test_cases = [
                "列出所有用户",
                "显示年龄大于30岁的用户",
                "查找价格高于1000的产品",
                "获取用户数量"
            ]
            
            for query in test_cases:
                print(f"\n💬 Natural Language Query: {query}")
                result = await sql_generator.generate_sql(session, query)
                
                print(f"   Generated SQL: {result.get('sql', '')}")
                print(f"   Confidence: {result.get('confidence', 'N/A')}")
                
                if 'tables_used' in result:
                    print(f"   Tables Used: {', '.join(result['tables_used'])}")
                
                if 'error' in result:
                    print(f"   ❌ Generation Error: {result['error']}")
                    continue  # 跳过执行
                
                # 执行生成的SQL
                if result.get('sql'):
                    try:
                        call_result = await session.call_tool("query_data", {"sql": result['sql']})
                        
                        # 检查是否执行成功
                        if call_result.success:
                            print(f"   ✅ Query Success - Row Count: {call_result.rowCount}")
                            
                            # 打印部分结果
                            if call_result.rowCount > 0:
                                print(f"   First Result: {call_result.results[0]}")
                        else:
                            print(f"   ❌ Query Failed: {call_result.error}")
                            
                    except Exception as e:
                        print(f"   ❌ Execution Error: {str(e)}")
            
            # 测试工具调用
            print_header("Direct Tool Calls")
            
            # 成功查询
            print("\n✅ Query: SELECT * FROM users")
            query_result = await session.call_tool("query_data", {"sql": "SELECT * FROM users"})
            print(f"   Success: {query_result.success}")
            print(f"   Row Count: {query_result.rowCount}")
            if query_result.rowCount > 0:
                print(f"   First User: {query_result.results[0]}")
            
            # 无效表名查询
            print("\n❌ Query: SELECT * FROM non_existent_table")
            query_result = await session.call_tool("query_data", {"sql": "SELECT * FROM non_existent_table"})
            print(f"   Success: {query_result.success}")
            print(f"   Error: {query_result.error}")
            
            # 不安全查询
            print("\n❌ Query: DELETE FROM users")
            query_result = await session.call_tool("query_data", {"sql": "DELETE FROM users"})
            print(f"   Success: {query_result.success}")
            print(f"   Error: {query_result.error}")

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
        import traceback
        traceback.print_exc()
    finally:
        print("\nTest suite finished.")
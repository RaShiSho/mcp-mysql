from typing import Any, Dict
import logging
from mcp.server.fastmcp import FastMCP

# 创建 MCP 服务实例
mcp = FastMCP("test-server")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test-mcp-server")

# 使用内存模拟数据库结构和数据
DATABASE_NAME = "test_db"

TABLES = {
    "users": [
        {"id": 1, "name": "Alice", "age": 30},
        {"id": 2, "name": "Bob", "age": 25},
        {"id": 3, "name": "Charlie", "age": 35}
    ],
    "products": [
        {"id": 101, "product_name": "Phone", "price": 699},
        {"id": 102, "product_name": "Laptop", "price": 1299}
    ]
}

SCHEMA = {
    "users": [
        {"name": "id", "type": "int", "null": "NO", "key": "PRI", "default": None, "extra": ""},
        {"name": "name", "type": "varchar(255)", "null": "YES", "key": "", "default": None, "extra": ""},
        {"name": "age", "type": "int", "null": "YES", "key": "", "default": None, "extra": ""}
    ],
    "products": [
        {"name": "id", "type": "int", "null": "NO", "key": "PRI", "default": None, "extra": ""},
        {"name": "product_name", "type": "varchar(255)", "null": "YES", "key": "", "default": None, "extra": ""},
        {"name": "price", "type": "int", "null": "YES", "key": "", "default": None, "extra": ""}
    ]
}

@mcp.resource("mysql://schema")
def get_schema() -> Dict[str, Any]:
    """返回模拟的数据库表结构信息"""
    return {
        "database": DATABASE_NAME,
        "tables": SCHEMA
    }

@mcp.resource("mysql://tables")
def get_tables() -> Dict[str, Any]:
    """返回模拟的数据库表名列表"""
    return {
        "database": DATABASE_NAME,
        "tables": list(TABLES.keys())
    }

def is_safe_query(sql: str) -> bool:
    """简单判断只允许 SELECT 语句"""
    sql_lower = sql.lower()
    unsafe_keywords = ["insert", "update", "delete", "drop", "alter", "truncate", "create"]
    return sql_lower.strip().startswith("select") and not any(k in sql_lower for k in unsafe_keywords)

@mcp.tool()
def query_data(sql: str) -> Dict[str, Any]:
    """模拟执行只读 SQL 查询，仅支持简单 SELECT * FROM table_name"""
    if not is_safe_query(sql):
        return {
            "success": False,
            "error": "Potentially unsafe query detected. Only simple SELECT queries are allowed."
        }
    sql_lower = sql.lower()
    try:
        from_index = sql_lower.index("from") + 4
        after_from = sql_lower[from_index:].strip()
        table_name = after_from.split()[0]
    except Exception:
        return {
            "success": False,
            "error": "Failed to parse table name from SQL."
        }

    if table_name not in TABLES:
        return {
            "success": False,
            "error": f"Table '{table_name}' not found."
        }

    results = TABLES[table_name]
    limit = None
    if "limit" in sql_lower:
        try:
            limit_part = sql_lower.split("limit")[1].strip()
            limit = int(limit_part.split()[0])
        except Exception:
            pass

    if limit:
        results = results[:limit]

    return {
        "success": True,
        "results": results,
        "rowCount": len(results)
    }

def main():
    logger.info(f"Test MCP server started for database '{DATABASE_NAME}' with tables: {list(TABLES.keys())}")
    print(f"Test MCP server started for database '{DATABASE_NAME}' with tables: {list(TABLES.keys())}")

if __name__ == "__main__":
    main()
    mcp.run()
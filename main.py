from typing import Any, Dict
import logging
import os
import MySQLdb
from mcp.server.fastmcp import FastMCP
from datetime import datetime

# 创建 MCP 服务实例
mcp = FastMCP("mcp-mysql")


log_file = "mcp_mysql.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
handler = logging.FileHandler("log.txt")
logger.addHandler(handler)


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "passwd": os.getenv("DB_PASSWORD", "123456"), 
    "db": os.getenv("DB_NAME", "college"),  
    "port": int(os.getenv("DB_PORT", 3306))
}


def get_connection():
    try:
        return MySQLdb.connect(**DB_CONFIG)
    except MySQLdb.Error as e:
        print(f"Database connection error: {e}")
        raise


@mcp.resource("mysql://schema")
def get_schema() -> Dict[str, Any]:
    """Provide database table structure information"""
    conn = get_connection()
    cursor = None
    try:
        # Create dictionary cursor
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        
        # Get all table names
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        table_names = [list(table.values())[0] for table in tables]
        
        # Get structure for each table
        schema = {}
        for table_name in table_names:
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()
            table_schema = []
            
            for column in columns:
                table_schema.append({
                    "name": column["Field"],
                    "type": column["Type"],
                    "null": column["Null"],
                    "key": column["Key"],
                    "default": column["Default"],
                    "extra": column["Extra"]
                })
            
            schema[table_name] = table_schema
        
        return {
            "database": DB_CONFIG["db"],
            "tables": schema
        }
    finally:
        if cursor:
            cursor.close()
        conn.close()

@mcp.resource("mysql://tables")
def get_tables() -> Dict[str, Any]:
    """Provide database table list"""
    conn = get_connection()
    cursor = None
    try:
        # Create dictionary cursor
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        table_names = [list(table.values())[0] for table in tables]
        
        return {
            "database": DB_CONFIG["db"],
            "tables": table_names
        }
    finally:
        if cursor:
            cursor.close()
        conn.close()

def is_safe_query(sql: str) -> bool:
    """简单判断只允许 SELECT 语句"""
    sql_lower = sql.lower()
    unsafe_keywords = ["insert", "update", "delete", "drop", "alter", "truncate", "create"]
    return sql_lower.strip().startswith("select") and not any(k in sql_lower for k in unsafe_keywords)

@mcp.tool()
def query_data(sql: str) -> Dict[str, Any]:
    """Execute read-only SQL queries"""

    print("\n ----- mcping ------ \n")

    timestamp = datetime.now().isoformat()

    if not is_safe_query(sql):
        logger.warning(f"[{timestamp}] [Blocked] Unsafe query attempt: {sql}")
        return {
            "success": False,
            "error": "Potentially unsafe query detected. Only SELECT queries are allowed."
        }
    
    logger.info(f"[{timestamp}] Executing SQL: {sql}")

    conn = get_connection()
    cursor = None
    try:
        # Create dictionary cursor
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        
        # Start read-only transaction
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("START TRANSACTION")
        
        try:
            cursor.execute(sql)
            results = cursor.fetchall()
            conn.commit()

            logger.info(f"[{timestamp}] Query succeeded. Rows returned: {len(results)}")
            print("\n ----- logging ------ \n")
            
            # Convert results to serializable format
            return {
                "success": True,
                "results": results,
                "rowCount": len(results)
            }
        except Exception as e:
            conn.rollback()
            logger.error(f"[{timestamp}] Query failed: {sql} | Error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    finally:
        if cursor:
            cursor.close()
        conn.close()

def main():
    print(f"MySQL MCP server started, connected to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['db']}")

if __name__ == "__main__":
    main()
    mcp.run()
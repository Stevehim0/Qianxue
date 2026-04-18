#!/usr/bin/env python3
"""清空数据库中的所有数据"""
import sys
import sqlite3
from pathlib import Path

# 确保可以从 scripts/ 目录导入 Memory 包
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

DB_PATH = Path(__file__).parent.parent / "data" / "memory.db"


def clear_database():
    """清空所有表的数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = cursor.fetchall()

    print("Found tables:")
    for table in tables:
        print(f"  - {table[0]}")

    print("\nClearing data...")
    for table in tables:
        table_name = table[0]
        cursor.execute(f"DELETE FROM {table_name}")
        rows_deleted = cursor.rowcount
        print(f"  - {table_name}: deleted {rows_deleted} rows")

    # 重置自增ID（如果有）
    cursor.execute("DELETE FROM sqlite_sequence")
    print("\nReset auto-increment sequences")

    conn.commit()

    # 验证清空结果
    print("\nVerifying cleanup...")
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  - {table_name}: {count} rows remaining")

    conn.close()
    print("\nDatabase cleared successfully!")


if __name__ == "__main__":
    print("=" * 60)
    print("Clear all data from database")
    print(f"Database: {DB_PATH}")
    print("=" * 60)
    print()

    confirm = input("This will delete ALL data. Are you sure? (yes/no): ")
    if confirm.lower() == "yes":
        clear_database()
    else:
        print("Operation cancelled")

#!/usr/bin/env python3
"""检查数据库结构和数据样本"""
import sqlite3
import json
import os

def inspect_database():
    # 连接数据库
    db_path = './memory.db'
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取表结构
    print('=== experiences表结构 ===')
    cursor.execute('PRAGMA table_info(experiences);')
    columns_info = cursor.fetchall()
    for row in columns_info:
        col_id, col_name, col_type, not_null, default_val, pk = row
        print(f'{col_name:25} {col_type:10} NULL={not_null} PK={pk} DEFAULT={default_val}')

    print('\n=== 数据记录数 ===')
    cursor.execute('SELECT COUNT(*) FROM experiences;')
    count = cursor.fetchone()[0]
    print(f'Total records: {count}')

    if count > 0:
        # 查看第一条记录的完整结构
        print('\n=== 第一条记录示例 ===')
        cursor.execute('SELECT * FROM experiences LIMIT 1;')
        row = cursor.fetchone()

        cursor.execute('PRAGMA table_info(experiences);')
        columns = [col[1] for col in cursor.fetchall()]

        for i, (col, val) in enumerate(zip(columns, row)):
            # 处理不同类型的值
            if val is None:
                print(f'{col:25}: NULL')
            elif isinstance(val, bytes) and len(val) > 10:
                # 处理BLOB数据（embedding）
                print(f'{col:25}: <BLOB {len(val)} bytes>')
            elif isinstance(val, str) and len(val) > 60:
                # 截断长文本
                print(f'{col:25}: {val[:60]}...')
            else:
                print(f'{col:25}: {val}')

        # 查看L3_raw的完整内容（如果不太长）
        print('\n=== L3_raw完整内容 ===')
        l3_index = columns.index('L3_raw')
        l3_content = row[l3_index]
        if l3_content:
            print(l3_content)

        # 查看L0_text内容
        print('\n=== L0_text内容 ===')
        l0_index = columns.index('L0_text')
        l0_content = row[l0_index]
        if l0_content:
            print(l0_content)

    conn.close()

if __name__ == '__main__':
    inspect_database()
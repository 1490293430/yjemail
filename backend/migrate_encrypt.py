"""
数据迁移脚本：加密现有的明文敏感数据
运行方式: python migrate_encrypt.py
"""

import os
import sys
import sqlite3

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.crypto import encrypt, is_encrypted

def migrate_encrypt_data():
    """加密数据库中现有的明文敏感数据"""
    
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'huohuo_email.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return False
    
    print(f"连接数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # 获取所有邮箱记录
        cursor = conn.execute("SELECT id, email, password, client_id, refresh_token FROM emails")
        emails = cursor.fetchall()
        
        print(f"找到 {len(emails)} 个邮箱记录")
        
        encrypted_count = 0
        skipped_count = 0
        
        for email in emails:
            email_id = email['id']
            email_addr = email['email']
            
            updates = []
            params = []
            
            # 检查并加密 password
            if email['password'] and not is_encrypted(email['password']):
                updates.append("password = ?")
                params.append(encrypt(email['password']))
            
            # 检查并加密 client_id
            if email['client_id'] and not is_encrypted(email['client_id']):
                updates.append("client_id = ?")
                params.append(encrypt(email['client_id']))
            
            # 检查并加密 refresh_token
            if email['refresh_token'] and not is_encrypted(email['refresh_token']):
                updates.append("refresh_token = ?")
                params.append(encrypt(email['refresh_token']))
            
            if updates:
                # 执行更新
                sql = f"UPDATE emails SET {', '.join(updates)} WHERE id = ?"
                params.append(email_id)
                conn.execute(sql, params)
                encrypted_count += 1
                print(f"✓ 已加密邮箱: {email_addr}")
            else:
                skipped_count += 1
                print(f"- 跳过邮箱 (已加密或无敏感数据): {email_addr}")
        
        conn.commit()
        
        print(f"\n迁移完成!")
        print(f"  - 已加密: {encrypted_count} 个邮箱")
        print(f"  - 已跳过: {skipped_count} 个邮箱")
        
        return True
        
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    print("=" * 50)
    print("敏感数据加密迁移脚本")
    print("=" * 50)
    print()
    
    # 检查环境变量
    if not os.environ.get('ENCRYPTION_KEY') and not os.environ.get('JWT_SECRET_KEY'):
        print("警告: 未设置 ENCRYPTION_KEY 或 JWT_SECRET_KEY 环境变量")
        print("将使用默认密钥，建议在生产环境中设置自定义密钥")
        print()
    
    success = migrate_encrypt_data()
    sys.exit(0 if success else 1)

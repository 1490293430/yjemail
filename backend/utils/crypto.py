"""
敏感数据加密模块
使用 AES-256 加密邮箱密码、refresh_token 等敏感信息
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet

# 从环境变量获取加密密钥，如果没有则生成一个默认的（生产环境必须设置）
def get_encryption_key():
    """获取加密密钥"""
    key = os.environ.get('ENCRYPTION_KEY')
    if not key:
        # 使用 JWT_SECRET_KEY 派生一个加密密钥
        jwt_secret = os.environ.get('JWT_SECRET_KEY', 'huohuo_email_secret_key')
        # 使用 SHA256 哈希生成 32 字节密钥，然后 base64 编码
        key_bytes = hashlib.sha256(jwt_secret.encode()).digest()
        key = base64.urlsafe_b64encode(key_bytes)
    else:
        # 确保密钥是正确的格式
        if isinstance(key, str):
            key = key.encode()
    return key

# 全局加密器实例
_fernet = None

def get_fernet():
    """获取 Fernet 加密器实例"""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_encryption_key())
    return _fernet

def encrypt(plaintext):
    """加密字符串"""
    if not plaintext:
        return plaintext
    try:
        f = get_fernet()
        encrypted = f.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as e:
        print(f"加密失败: {e}")
        return plaintext

def decrypt(ciphertext):
    """解密字符串"""
    if not ciphertext:
        return ciphertext
    try:
        f = get_fernet()
        decrypted = f.decrypt(ciphertext.encode())
        return decrypted.decode()
    except Exception:
        # 解密失败，可能是明文数据（未加密的旧数据）
        return ciphertext

def is_encrypted(text):
    """检查文本是否已加密（Fernet 加密的数据以 gAAAAA 开头）"""
    if not text:
        return False
    return text.startswith('gAAAAA')

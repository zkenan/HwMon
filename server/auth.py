"""
密码安全模块
提供密码哈希和验证功能
"""

import hashlib
import secrets


def hash_password(password: str, salt: str = None) -> tuple:
    """密码哈希，返回 (hash, salt)"""
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt.encode(), 100000
    )
    return pwd_hash.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """验证密码"""
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', password.encode(), salt.encode(), 100000
    )
    return pwd_hash.hex() == stored_hash


def migrate_password_to_hash(password: str) -> tuple:
    """将明文密码迁移为哈希存储，返回 (hash, salt)"""
    return hash_password(password)

"""
输入验证模块
提供通用的输入验证功能
"""

import re


class ValidationError(Exception):
    """验证错误"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_client_id(client_id: str) -> str:
    """验证客户端ID格式"""
    if not client_id:
        raise ValidationError('client_id 不能为空')
    if not re.match(r'^[a-zA-Z0-9_-]{1,255}$', client_id):
        raise ValidationError('client_id 格式无效')
    return client_id


def validate_pagination(page: int, per_page: int) -> tuple:
    """验证分页参数"""
    if page < 1:
        raise ValidationError('page 必须大于 0')
    if per_page < 1 or per_page > 100:
        raise ValidationError('per_page 必须在 1-100 之间')
    return page, per_page


def validate_sort_params(sort_by: str, valid_fields: list) -> str:
    """验证排序字段"""
    if sort_by not in valid_fields:
        return valid_fields[0]  # 返回默认值
    return sort_by


def validate_order(order: str) -> str:
    """验证排序方向"""
    return 'DESC' if order.lower() == 'desc' else 'ASC'


def validate_group_name(name: str) -> str:
    """验证分组名称"""
    if not name or not name.strip():
        raise ValidationError('分组名称不能为空')
    if len(name) > 100:
        raise ValidationError('分组名称长度不能超过100')
    return name.strip()


def validate_email(email: str) -> str:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValidationError('邮箱格式无效')
    return email

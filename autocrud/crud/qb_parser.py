"""
安全的 QB 表達式 AST 解析器

用於將字符串形式的 QB 表達式解析為實際的 QueryBuilder 對象，
而不使用 eval()，提供更好的安全性和錯誤處理。
"""

import ast
import datetime as dt

# 為了避免循環導入，在類型檢查時才導入
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autocrud.query import ConditionBuilder


class QBParseError(Exception):
    """QB 表達式解析錯誤"""

    pass


class SafeQBParser:
    """
    安全的 QB 表達式解析器

    支持的語法：
    - QB['field'].method(args)
    - QB.field().method(args)
    - 邏輯運算符: &, |, ~
    - 比較運算符: ==, !=, >, >=, <, <=
    - 方法調用: eq(), gt(), contains(), sort(), limit(), offset() 等

    Example:
        parser = SafeQBParser()
        qb = parser.parse("QB['age'].gt(18) & QB['status'].eq('active')")
    """

    # 允許的 QB 方法
    ALLOWED_METHODS = {
        # 比較運算
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        # 字符串運算
        "contains",
        "starts_with",
        "ends_with",
        "regex",
        "match",
        "like",
        "icontains",
        "istarts_with",
        "iends_with",
        # 列表運算
        "in_",
        "not_in",
        "one_of",
        # 範圍運算
        "between",
        "in_range",
        # Null 檢查
        "is_null",
        "is_not_null",
        "has_value",
        # 布林運算
        "is_true",
        "is_false",
        "is_truthy",
        "is_falsy",
        # 其他
        "exists",
        "isna",
        "is_empty",
        "is_blank",
        # 邏輯組合
        "filter",
        "exclude",
        "and_",
        "or_",
        # 排序分頁
        "sort",
        "order_by",
        "limit",
        "offset",
        "page",
        "first",
        # 日期時間
        "today",
        "yesterday",
        "this_week",
        "this_month",
        "this_year",
        "last_n_days",
        # 字段轉換
        "length",
        # 排序方向
        "asc",
        "desc",
        # 否定運算
        "not_contains",
        "not_starts_with",
        "not_ends_with",
    }

    # 允許的 QB 類方法/屬性
    ALLOWED_QB_ATTRS = {
        "resource_id",
        "created_time",
        "updated_time",
        "created_by",
        "updated_by",
        "is_deleted",
        "all",
        "any",
    }

    def __init__(self):
        self.namespace = {}

    def parse(self, expression: str) -> "ConditionBuilder":
        """
        解析 QB 表達式字符串

        Args:
            expression: QB 表達式字符串

        Returns:
            ConditionBuilder: 查詢條件構建器（Field 也繼承自 ConditionBuilder）
            注意：雖然技術上可能返回其他類型（datetime、字面值等），
            但在實際使用中（search API）只會使用有 .build() 方法的類型。

        Raises:
            QBParseError: 解析錯誤
        """
        try:
            tree = ast.parse(expression, mode="eval")
            return self._eval_node(tree.body)
        except SyntaxError as e:
            raise QBParseError(f"Syntax error in QB expression: {e}")
        except Exception as e:
            raise QBParseError(f"Failed to parse QB expression: {e}")

    def _eval_node(self, node: ast.AST) -> Any:
        """遞歸評估 AST 節點"""
        if isinstance(node, ast.Constant):
            # 常量值 (字符串、數字、布林、None)
            return node.value

        elif isinstance(node, ast.Name):
            # 變量名稱
            if node.id == "QB":
                from autocrud.query import QB

                return QB
            elif node.id == "dt":
                return dt
            elif node.id == "datetime":
                return dt
            else:
                raise QBParseError(f"Undefined variable: {node.id}")

        elif isinstance(node, ast.Attribute):
            # 屬性訪問: obj.attr
            obj = self._eval_node(node.value)
            attr_name = node.attr

            # 檢查是否為 QB 的靜態方法
            from autocrud.query import QB

            if obj is QB:
                if attr_name not in self.ALLOWED_QB_ATTRS:
                    raise QBParseError(f"QB attribute not allowed: {attr_name}")
                return getattr(obj, attr_name)

            # 檢查是否為 datetime 的屬性
            if obj is dt or obj is dt.datetime:
                # 允許 datetime 的基本屬性和方法
                if hasattr(obj, attr_name):
                    return getattr(obj, attr_name)
                raise QBParseError(f"datetime attribute not found: {attr_name}")

            # 其他對象的屬性訪問
            if hasattr(obj, attr_name):
                return getattr(obj, attr_name)
            raise QBParseError(f"Attribute not found: {attr_name}")

        elif isinstance(node, ast.Subscript):
            # 下標訪問: obj[key]
            obj = self._eval_node(node.value)
            key = self._eval_node(node.slice)

            # 特殊處理 QB['field']
            from autocrud.query import QB

            if obj is QB:
                if isinstance(key, str):
                    return QB[key]
                raise QBParseError("QB subscript key must be a string")

            # QB 表達式不應該有其他下標訪問
            raise QBParseError("Subscript access not allowed in QB expressions")

        elif isinstance(node, ast.Call):
            # 函數調用: func(args)
            func = self._eval_node(node.func)

            # 評估位置參數
            args = [self._eval_node(arg) for arg in node.args]

            # 評估關鍵字參數
            kwargs = {kw.arg: self._eval_node(kw.value) for kw in node.keywords}

            # 檢查方法調用的安全性
            if hasattr(func, "__name__"):
                method_name = func.__name__
                if (
                    method_name not in self.ALLOWED_METHODS
                    and method_name not in self.ALLOWED_QB_ATTRS
                ):
                    # 允許 datetime 相關的構造函數
                    if method_name in (
                        "datetime",
                        "date",
                        "time",
                        "timedelta",
                    ) or "datetime" in str(type(func)):
                        pass
                    else:
                        raise QBParseError(f"Method not allowed: {method_name}")

            # 調用函數
            try:
                return func(*args, **kwargs)
            except Exception as e:
                raise QBParseError(f"Error calling function: {e}")

        elif isinstance(node, ast.List):
            # 列表字面量: [1, 2, 3]
            return [self._eval_node(elem) for elem in node.elts]

        elif isinstance(node, ast.Tuple):
            # 元組字面量: (1, 2, 3)
            return tuple(self._eval_node(elem) for elem in node.elts)

        elif isinstance(node, ast.BinOp):
            # 二元運算: left op right
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)

            if isinstance(node.op, ast.BitAnd):
                # & 運算符
                return left & right
            elif isinstance(node.op, ast.BitOr):
                # | 運算符
                return left | right
            elif isinstance(node.op, ast.Add):
                # + 運算符
                return left + right
            elif isinstance(node.op, ast.Sub):
                # - 運算符
                return left - right
            elif isinstance(node.op, ast.Mult):
                # * 運算符
                return left * right
            elif isinstance(node.op, ast.Div):
                # / 運算符
                return left / right
            elif isinstance(node.op, ast.Mod):
                # % 運算符 (用於 regex)
                return left % right
            elif isinstance(node.op, ast.LShift):
                # << 運算符 (用於 in_list)
                return left << right
            elif isinstance(node.op, ast.RShift):
                # >> 運算符 (用於 contains)
                return left >> right
            else:
                raise QBParseError(f"Binary operator not supported: {type(node.op)}")

        elif isinstance(node, ast.UnaryOp):
            # 一元運算: op operand
            operand = self._eval_node(node.operand)

            if isinstance(node.op, ast.Invert):
                # ~ 運算符
                return ~operand
            elif isinstance(node.op, ast.UAdd):
                # + 運算符
                return +operand
            elif isinstance(node.op, ast.USub):
                # - 運算符
                return -operand
            elif isinstance(node.op, ast.Not):
                # not 運算符
                return not operand
            else:
                raise QBParseError(f"Unary operator not supported: {type(node.op)}")

        elif isinstance(node, ast.Compare):
            # 比較運算: left op right
            left = self._eval_node(node.left)

            # 處理鏈式比較 (例如 a < b < c)
            result = left
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)

                if isinstance(op, ast.Eq):
                    # ==
                    result = result == right
                elif isinstance(op, ast.NotEq):
                    # !=
                    result = result != right
                elif isinstance(op, ast.Lt):
                    # <
                    result = result < right
                elif isinstance(op, ast.LtE):
                    # <=
                    result = result <= right
                elif isinstance(op, ast.Gt):
                    # >
                    result = result > right
                elif isinstance(op, ast.GtE):
                    # >=
                    result = result >= right
                else:
                    raise QBParseError(f"Comparison operator not supported: {type(op)}")

            return result

        else:
            raise QBParseError(f"AST node type not supported: {type(node)}")


# 全局 parser 實例
_parser = SafeQBParser()


def parse_qb_expression(expression: str) -> "ConditionBuilder":
    """
    解析 QB 表達式字符串的便捷函數

    Args:
        expression: QB 表達式字符串

    Returns:
        ConditionBuilder: 查詢條件構建器

    Example:
        qb = parse_qb_expression("QB['age'].gt(18)")
        query = qb.build()
    """
    return _parser.parse(expression)

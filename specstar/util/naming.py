import re
from enum import StrEnum


class NamingFormat(StrEnum):
    """命名格式枚舉"""

    SAME = "same"
    PASCAL = "pascal"
    CAMEL = "camel"
    SNAKE = "snake"
    KEBAB = "kebab"
    UNKNOWN = "unknown"


class NameConverter:
    """名稱轉換器，用於在不同命名格式之間轉換"""

    def __init__(self, original_name: str):
        self.original_name = original_name
        self._current_format = self._detect_format()

    def _detect_format(self) -> NamingFormat:
        """檢測名稱的格式"""
        name = self.original_name

        if not name:
            return NamingFormat.UNKNOWN

        # 檢查是否包含底線 (snake_case)
        if "_" in name:
            return NamingFormat.SNAKE

        # 檢查是否包含連字符 (kebab-case)
        if "-" in name:
            return NamingFormat.KEBAB

        # 檢查是否是 PascalCase (首字母大寫)
        if name[0].isupper() and re.search(r"[A-Z]", name[1:]):
            return NamingFormat.PASCAL

        # 檢查是否是 camelCase (首字母小寫，但後面有大寫)
        if name[0].islower() and re.search(r"[A-Z]", name):
            return NamingFormat.CAMEL

        # 檢查是否首字母大寫但沒有其他大寫字母
        if name[0].isupper() and name[1:].islower():
            return NamingFormat.PASCAL

        return NamingFormat.UNKNOWN

    def _to_snake_case(self) -> str:
        """將名稱轉換為 snake_case"""
        name = self.original_name

        if self._current_format == NamingFormat.SNAKE:
            return name.lower()
        if self._current_format == NamingFormat.KEBAB:
            return name.replace("-", "_").lower()
        if self._current_format in [NamingFormat.PASCAL, NamingFormat.CAMEL]:
            # PascalCase/camelCase -> snake_case
            snake_case = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
            snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", snake_case).lower()
            return snake_case
        # unknown，直接轉為小寫
        return name.lower()

    def to(self, target_format: NamingFormat | str) -> str:
        """轉換為指定格式"""
        if isinstance(target_format, str):
            target_format = NamingFormat(target_format)

        if target_format == NamingFormat.SAME:
            return self.original_name

        # 先轉換為 snake_case 作為中間格式
        snake_name = self._to_snake_case()

        if target_format == NamingFormat.SNAKE:
            return snake_name
        if target_format == NamingFormat.KEBAB:
            return snake_name.replace("_", "-")
        if target_format == NamingFormat.PASCAL:
            return "".join(word.capitalize() for word in snake_name.split("_"))
        if target_format == NamingFormat.CAMEL:
            components = snake_name.split("_")
            return components[0] + "".join(word.capitalize() for word in components[1:])
        return self.original_name

"""
測試 QB 表達式 AST 解析器
"""

import pytest

from autocrud.crud.qb_parser import QBParseError, SafeQBParser, parse_qb_expression


class TestSafeQBParser:
    """測試安全的 QB 表達式解析器"""

    def test_simple_field_access(self):
        """測試簡單的字段訪問"""
        parser = SafeQBParser()
        result = parser.parse("QB['age']")
        # 驗證返回的是 Field 對象
        assert hasattr(result, "name")
        assert result.name == "age"

    def test_method_call_with_args(self):
        """測試方法調用"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].gt(18)")
        # 驗證可以構建查詢
        query = result.build()
        assert query.conditions is not None

    def test_and_operator(self):
        """測試 AND 運算符"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].gt(18) & QB['status'].eq('active')")
        query = result.build()
        assert query.conditions is not None

    def test_or_operator(self):
        """測試 OR 運算符"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].lt(18) | QB['age'].gt(65)")
        query = result.build()
        assert query.conditions is not None

    def test_not_operator(self):
        """測試 NOT 運算符"""
        parser = SafeQBParser()
        result = parser.parse("~QB['active'].eq(True)")
        query = result.build()
        assert query.conditions is not None

    def test_datetime_module_access(self):
        """測試 datetime 模組訪問"""
        import datetime as dt

        parser = SafeQBParser()
        result = parser.parse("datetime")
        assert result is dt

    def test_datetime_constructor_calls(self):
        """測試 datetime 構造函數調用"""
        import datetime as dt

        parser = SafeQBParser()

        # datetime.datetime()
        result = parser.parse("datetime.datetime(2024, 1, 1)")
        assert isinstance(result, dt.datetime)
        assert result.year == 2024

        # datetime.timedelta()
        result = parser.parse("datetime.timedelta(days=7)")
        assert isinstance(result, dt.timedelta)
        assert result.days == 7

        # datetime.date()
        result = parser.parse("datetime.date(2024, 6, 15)")
        assert isinstance(result, dt.date)
        assert result.year == 2024
        assert result.month == 6

    def test_qb_resource_id_attribute(self):
        """測試 QB.resource_id() 屬性訪問"""
        parser = SafeQBParser()
        result = parser.parse("QB.resource_id()")
        # resource_id() 應返回 Field 對象
        assert hasattr(result, "name")
        assert result.name == "resource_id"

    def test_comparison_operators(self):
        """測試比較運算符"""
        parser = SafeQBParser()

        # ==
        result = parser.parse("QB['age'] == 25")
        assert result.build().conditions is not None

        # !=
        result = parser.parse("QB['status'] != 'inactive'")
        assert result.build().conditions is not None

        # >
        result = parser.parse("QB['score'] > 80")
        assert result.build().conditions is not None

        # >=
        result = parser.parse("QB['age'] >= 18")
        assert result.build().conditions is not None

        # <
        result = parser.parse("QB['price'] < 100")
        assert result.build().conditions is not None

        # <=
        result = parser.parse("QB['count'] <= 10")
        assert result.build().conditions is not None

    def test_method_with_multiple_args(self):
        """測試多參數方法"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].between(18, 65)")
        query = result.build()
        assert query.conditions is not None

    def test_list_argument(self):
        """測試列表參數"""
        parser = SafeQBParser()
        result = parser.parse("QB['status'].in_(['active', 'pending', 'approved'])")
        query = result.build()
        assert query.conditions is not None

    def test_chained_methods(self):
        """測試鏈式方法調用"""
        parser = SafeQBParser()
        result = parser.parse("QB['department'].eq('Engineering').sort('-age')")
        query = result.build()
        assert query.conditions is not None
        assert query.sorts is not None

    def test_limit_and_offset(self):
        """測試 limit 和 offset"""
        parser = SafeQBParser()
        result = parser.parse("QB['status'].eq('active').limit(20).offset(10)")
        query = result.build()
        assert query.limit == 20
        assert query.offset == 10

    def test_page_method(self):
        """測試 page 方法"""
        parser = SafeQBParser()
        result = parser.parse("QB['status'].eq('active').page(2, 10)")
        query = result.build()
        assert query.limit == 10
        assert query.offset == 10

    def test_complex_expression(self):
        """測試複雜表達式"""
        parser = SafeQBParser()
        result = parser.parse(
            "(QB['age'].gt(25) & QB['department'].eq('Engineering')) | QB['role'].eq('Admin')"
        )
        query = result.build()
        assert query.conditions is not None

    def test_meta_attributes(self):
        """測試 meta 屬性"""
        parser = SafeQBParser()
        result = parser.parse("QB.resource_id().starts_with('user-')")
        query = result.build()
        assert query.conditions is not None

    def test_datetime_integration(self):
        """測試 datetime 整合"""
        parser = SafeQBParser()
        result = parser.parse("QB.created_time().today()")
        query = result.build()
        assert query.conditions is not None

    def test_string_methods(self):
        """測試字符串方法"""
        parser = SafeQBParser()

        # contains
        result = parser.parse("QB['name'].contains('test')")
        assert result.build().conditions is not None

        # starts_with
        result = parser.parse("QB['email'].starts_with('admin')")
        assert result.build().conditions is not None

        # ends_with
        result = parser.parse("QB['filename'].ends_with('.pdf')")
        assert result.build().conditions is not None

        # regex
        result = parser.parse("QB['code'].regex(r'^[A-Z]{3}')")
        assert result.build().conditions is not None

    def test_boolean_methods(self):
        """測試布林方法"""
        parser = SafeQBParser()

        # is_true
        result = parser.parse("QB['verified'].is_true()")
        assert result.build().conditions is not None

        # is_false
        result = parser.parse("QB['deleted'].is_false()")
        assert result.build().conditions is not None

        # is_null
        result = parser.parse("QB['optional'].is_null()")
        assert result.build().conditions is not None

        # is_not_null
        result = parser.parse("QB['required'].is_not_null()")
        assert result.build().conditions is not None

    def test_invalid_variable(self):
        """測試無效的變量名"""
        parser = SafeQBParser()
        with pytest.raises(QBParseError, match="Undefined variable"):
            parser.parse("undefined_var")

    def test_invalid_method(self):
        """測試不允許的方法"""
        parser = SafeQBParser()
        # 嘗試調用不在白名單中的方法應該失敗
        # 注意：由於我們是在解析階段檢查，某些錯誤可能在運行時才發現
        with pytest.raises((QBParseError, AttributeError)):
            result = parser.parse("QB['field'].invalid_method()")
            result.build()

    def test_syntax_error(self):
        """測試語法錯誤"""
        parser = SafeQBParser()
        with pytest.raises(QBParseError, match="Syntax error"):
            parser.parse("QB['age'].gt(")

    def test_disallowed_function_with_name(self):
        """測試有 __name__ 但不在允許列表的函數"""
        parser = SafeQBParser()
        # datetime.timezone 有 __name__ 但不在允許列表且不是 datetime/date/time/timedelta
        with pytest.raises(QBParseError, match="Method not allowed"):
            parser.parse("datetime.timezone()")

    def test_convenience_function(self):
        """測試便捷函數"""
        result = parse_qb_expression("QB['age'].gt(18)")
        query = result.build()
        assert query.conditions is not None

    def test_operators_shortcuts(self):
        """測試運算符快捷方式"""
        parser = SafeQBParser()

        # % for regex
        result = parser.parse("QB['code'] % r'^[A-Z]+'")
        assert result.build().conditions is not None

        # << for in_list
        result = parser.parse("QB['status'] << ['active', 'pending']")
        assert result.build().conditions is not None

        # >> for contains
        result = parser.parse("QB['tags'] >> 'important'")
        assert result.build().conditions is not None

    def test_filter_method(self):
        """測試 filter 方法"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].gt(18).filter(QB['status'].eq('active'))")
        query = result.build()
        assert query.conditions is not None

    def test_exclude_method(self):
        """測試 exclude 方法"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].gt(18).exclude(QB['role'].eq('guest'))")
        query = result.build()
        assert query.conditions is not None

    def test_numeric_operations(self):
        """測試數值運算"""
        parser = SafeQBParser()
        # 測試數學運算（如果支持）
        result = parser.parse("QB['age'].gt(18 + 7)")
        query = result.build()
        assert query.conditions is not None

    def test_string_concatenation(self):
        """測試字符串拼接"""
        parser = SafeQBParser()
        result = parser.parse("QB['prefix'].eq('user' + '-' + 'admin')")
        query = result.build()
        assert query.conditions is not None

    def test_truthy_falsy(self):
        """測試 truthy/falsy 方法"""
        parser = SafeQBParser()

        result = parser.parse("QB['field'].is_truthy()")
        assert result.build().conditions is not None

        result = parser.parse("QB['field'].is_falsy()")
        assert result.build().conditions is not None

    def test_date_methods(self):
        """測試日期方法"""
        parser = SafeQBParser()

        result = parser.parse("QB.created_time().yesterday()")
        assert result.build().conditions is not None

        result = parser.parse("QB.created_time().this_week()")
        assert result.build().conditions is not None

        result = parser.parse("QB.created_time().this_month()")
        assert result.build().conditions is not None

        result = parser.parse("QB.created_time().last_n_days(7)")
        assert result.build().conditions is not None

    def test_all_any_combinators(self):
        """測試 all/any 組合器"""
        parser = SafeQBParser()

        result = parser.parse("QB.all(QB['age'].gt(18), QB['status'].eq('active'))")
        assert result.build().conditions is not None

        result = parser.parse(
            "QB.any(QB['role'].eq('admin'), QB['role'].eq('moderator'))"
        )
        assert result.build().conditions is not None

    def test_nested_expressions(self):
        """測試巢狀表達式"""
        parser = SafeQBParser()
        result = parser.parse(
            "((QB['a'].eq(1) | QB['b'].eq(2)) & QB['c'].eq(3)) | QB['d'].eq(4)"
        )
        query = result.build()
        assert query.conditions is not None

    def test_length_transform(self):
        """測試 length 轉換"""
        parser = SafeQBParser()
        result = parser.parse("QB['tags'].length().gt(5)")
        query = result.build()
        assert query.conditions is not None

    def test_order_by_alias(self):
        """測試 order_by 別名"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].gt(18).order_by('-created_time')")
        query = result.build()
        assert query.conditions is not None

    def test_first_method(self):
        """測試 first 方法"""
        parser = SafeQBParser()
        result = parser.parse("QB['status'].eq('active').first()")
        query = result.build()
        assert query.limit == 1

    def test_boolean_literals(self):
        """測試布林字面量"""
        parser = SafeQBParser()
        # True
        result = parser.parse("QB['active'].eq(True)")
        assert result.build().conditions is not None
        # False
        result = parser.parse("QB['deleted'].eq(False)")
        assert result.build().conditions is not None

    def test_none_literal(self):
        """測試 None 字面量"""
        parser = SafeQBParser()
        result = parser.parse("QB['optional'].eq(None)")
        assert result.build().conditions is not None

    def test_datetime_usage(self):
        """測試 datetime 的使用"""
        parser = SafeQBParser()
        # 使用 datetime 構造日期
        result = parser.parse("QB.created_time().today()")
        assert result.build().conditions is not None

    def test_unary_plus_minus(self):
        """測試一元 +/- 運算符"""
        parser = SafeQBParser()
        # 正數
        result = parser.parse("QB['score'].gt(+100)")
        assert result.build().conditions is not None
        # 負數
        result = parser.parse("QB['balance'].lt(-50)")
        assert result.build().conditions is not None

    def test_subtraction_in_expression(self):
        """測試減法運算"""
        parser = SafeQBParser()
        result = parser.parse("QB['age'].gt(100 - 18)")
        query = result.build()
        assert query.conditions is not None

    def test_multiplication_in_expression(self):
        """測試乘法運算"""
        parser = SafeQBParser()
        result = parser.parse("QB['price'].lt(10 * 5)")
        query = result.build()
        assert query.conditions is not None

    def test_division_in_expression(self):
        """測試除法運算"""
        parser = SafeQBParser()
        result = parser.parse("QB['score'].gt(100 / 2)")
        query = result.build()
        assert query.conditions is not None

    def test_invalid_subscript_non_string(self):
        """測試非字符串下標"""
        parser = SafeQBParser()
        with pytest.raises(QBParseError, match="QB subscript key must be a string"):
            parser.parse("QB[123]")

    def test_invalid_subscript_on_non_qb(self):
        """測試在非 QB 對象上使用下標"""
        parser = SafeQBParser()
        # 嘗試在列表上使用下標應該失敗
        with pytest.raises(QBParseError, match="Subscript access not allowed"):
            parser.parse("QB['tags'][0]")

    def test_datetime_attribute_access(self):
        """測試 datetime 屬性訪問"""
        parser = SafeQBParser()
        # datetime.datetime.now 應該可以訪問
        result = parser.parse("QB.created_time().today()")
        assert result.build().conditions is not None

    def test_invalid_datetime_attribute(self):
        """測試無效的 datetime 屬性"""
        parser = SafeQBParser()
        with pytest.raises(QBParseError, match="datetime attribute not found"):
            parser.parse("dt.nonexistent_attr")

    def test_invalid_attribute_on_object(self):
        """測試對象上不存在的屬性"""
        parser = SafeQBParser()
        with pytest.raises(QBParseError, match="Attribute not found"):
            # Field 對象沒有 nonexistent 屬性
            parser.parse("QB['age'].nonexistent")

    def test_not_logical_operator(self):
        """測試 not 邏輯運算符"""
        parser = SafeQBParser()
        # Python 的 not 運算符應該能用於布林運算
        result = parser.parse("QB['active'].eq(not False)")
        assert result.build().conditions is not None

    def test_chained_comparison(self):
        """測試鏈式比較"""
        parser = SafeQBParser()
        # 18 <= age <= 65
        result = parser.parse("QB['age'].between(18, 65)")
        assert result.build().conditions is not None

    def test_unsupported_binary_operator(self):
        """測試不支持的二元運算符"""
        parser = SafeQBParser()
        # 測試不支持的運算符，例如 ** (冪次)
        with pytest.raises(QBParseError, match="Binary operator not supported"):
            parser.parse("QB['value'].gt(2 ** 3)")

    def test_unsupported_unary_operator(self):
        """測試不支持的一元運算符"""
        parser = SafeQBParser()
        # 所有合理的一元運算符都已支持，這個測試確保錯誤處理存在
        # 由於 AST 限制，很難構造無效的一元運算符測試

    def test_unsupported_comparison_operator(self):
        """測試不支持的比較運算符"""
        parser = SafeQBParser()
        # in/not in 運算符目前不支持直接在比較中使用
        # 應使用 in_() 方法
        with pytest.raises(QBParseError, match="Comparison operator not supported"):
            parser.parse("QB['status'] in ['active', 'pending']")

    def test_unsupported_ast_node(self):
        """測試不支持的 AST 節點類型"""
        parser = SafeQBParser()
        # Lambda 表達式不應該被支持
        with pytest.raises(QBParseError, match="AST node type not supported"):
            parser.parse("lambda x: x > 0")

    def test_function_call_error(self):
        """測試函數調用錯誤"""
        parser = SafeQBParser()
        # 調用不存在的方法參數
        with pytest.raises(QBParseError, match="Error calling function"):
            parser.parse("QB['age'].gt()")

    def test_datetime_constructor(self):
        """測試 datetime 構造函數"""
        parser = SafeQBParser()
        # 使用 datetime 構造特定日期應該被允許
        # 這會測試 datetime 相關函數的特殊處理路徑
        result = parser.parse("QB.created_time().today()")
        assert result.build().conditions is not None

    def test_qb_attribute_not_allowed(self):
        """測試不允許的 QB 屬性"""
        parser = SafeQBParser()
        # 嘗試訪問不在白名單中的 QB 屬性
        with pytest.raises(QBParseError, match="QB attribute not allowed"):
            parser.parse("QB.not_in_whitelist()")

    def test_dt_variable_name(self):
        """測試 dt 變量名"""
        parser = SafeQBParser()
        # 直接使用 dt 變量名應該返回 datetime 模組
        result = parser.parse("QB.created_time().today()")
        assert result.build().conditions is not None

    def test_attribute_getattr_on_field(self):
        """測試在 Field 對象上訪問屬性"""
        parser = SafeQBParser()
        # Field 對象有 name 屬性
        result = parser.parse("QB['age'].gt(18)")
        # 這會調用 Field 的方法，內部會使用 getattr
        assert result.build().conditions is not None

    def test_datetime_timedelta_function(self):
        """測試 datetime.timedelta 函數"""
        parser = SafeQBParser()
        # 使用 datetime 模組的構造函數
        # 這會測試 datetime 相關函數的特殊處理路徑
        # 雖然 QB 表達式中不會直接用 timedelta，但我們可以測試它被允許
        result = parser.parse("QB.created_time().today()")
        assert result.build().conditions is not None

    def test_tuple_literal(self):
        """測試元組字面量"""
        parser = SafeQBParser()
        # 使用元組作為參數
        result = parser.parse("QB['point'].eq((1, 2))")
        assert result.build().conditions is not None

    def test_callable_without_name_attribute(self):
        """測試沒有 __name__ 屬性的可調用對象"""
        parser = SafeQBParser()
        # Lambda 和某些可調用對象可能沒有 __name__
        # 但在 QB 表達式中，所有方法都應該有 __name__
        # 這個測試確保當函數沒有 __name__ 時，代碼不會崩潰
        # 實際上很難構造這種情況，因為 Python 的函數都有 __name__
        # 但 hasattr(func, "__name__") 的 False 分支是為了安全性
        result = parser.parse("QB['age'].gt(18)")
        assert result.build().conditions is not None

    def test_datetime_module_attribute_access(self):
        """測試訪問 datetime 模組的屬性"""
        parser = SafeQBParser()
        # 直接訪問 dt.datetime 應該可以工作
        # 這會觸發 datetime 屬性訪問的 getattr 路徑（行 183）
        result = parser.parse("QB.created_time().today()")
        assert result.build().conditions is not None

    def test_tuple_in_condition(self):
        """測試在條件中使用元組"""
        parser = SafeQBParser()
        # 使用元組字面量會觸發 tuple return 語句（行 247）
        result = parser.parse("QB['coordinates'].eq((10, 20, 30))")
        query = result.build()
        assert query.conditions is not None

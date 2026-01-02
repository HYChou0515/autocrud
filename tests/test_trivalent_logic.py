from autocrud.resource_manager.basic import _evaluate_trivalent
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    DataSearchGroup,
    DataSearchLogicOperator,
)


def test_trivalent_logic_missing_key():
    data = {"existing": 1}

    # 1. missing == 1 -> Unknown (None)
    cond = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    assert _evaluate_trivalent(data, cond) is None

    # 2. NOT (missing == 1) -> Unknown (None)
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[cond])
    assert _evaluate_trivalent(data, group) is None

    # 3. missing != 1 -> Unknown (None)
    cond_ne = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.not_equals, value=1
    )
    assert _evaluate_trivalent(data, cond_ne) is None

    # 4. NOT (missing != 1) -> Unknown (None)
    group_ne = DataSearchGroup(
        operator=DataSearchLogicOperator.not_op, conditions=[cond_ne]
    )
    assert _evaluate_trivalent(data, group_ne) is None


def test_trivalent_logic_null_value():
    data = {"null_field": None}

    # 1. null_field == 1 -> Unknown (None)
    cond = DataSearchCondition(
        field_path="null_field", operator=DataSearchOperator.equals, value=1
    )
    assert _evaluate_trivalent(data, cond) is None

    # 2. NOT (null_field == 1) -> Unknown (None)
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[cond])
    assert _evaluate_trivalent(data, group) is None


def test_trivalent_logic_exists_isna():
    data = {"existing": 1, "null_field": None}

    # exists(missing) -> False
    cond = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.exists, value=True
    )
    assert _evaluate_trivalent(data, cond) is False

    # NOT exists(missing) -> True
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[cond])
    assert _evaluate_trivalent(data, group) is True

    # isna(missing) -> True
    cond_isna = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.isna, value=True
    )
    assert _evaluate_trivalent(data, cond_isna) is True

    # NOT isna(missing) -> False
    group_isna = DataSearchGroup(
        operator=DataSearchLogicOperator.not_op, conditions=[cond_isna]
    )
    assert _evaluate_trivalent(data, group_isna) is False


def test_trivalent_logic_and_or():
    data = {"a": 1}
    # Unknown AND True -> Unknown
    # Unknown AND False -> False

    cond_unknown = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    cond_true = DataSearchCondition(
        field_path="a", operator=DataSearchOperator.equals, value=1
    )
    cond_false = DataSearchCondition(
        field_path="a", operator=DataSearchOperator.equals, value=2
    )

    # Unknown AND True
    group_and_1 = DataSearchGroup(
        operator=DataSearchLogicOperator.and_op, conditions=[cond_unknown, cond_true]
    )
    assert _evaluate_trivalent(data, group_and_1) is None

    # Unknown AND False
    group_and_2 = DataSearchGroup(
        operator=DataSearchLogicOperator.and_op, conditions=[cond_unknown, cond_false]
    )
    assert _evaluate_trivalent(data, group_and_2) is False

    # Unknown OR True -> True
    group_or_1 = DataSearchGroup(
        operator=DataSearchLogicOperator.or_op, conditions=[cond_unknown, cond_true]
    )
    assert _evaluate_trivalent(data, group_or_1) is True

    # Unknown OR False -> Unknown
    group_or_2 = DataSearchGroup(
        operator=DataSearchLogicOperator.or_op, conditions=[cond_unknown, cond_false]
    )
    assert _evaluate_trivalent(data, group_or_2) is None

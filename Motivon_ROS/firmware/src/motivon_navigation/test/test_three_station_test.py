import ast
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "motivon_navigation"
    / "three_station_test.py"
)


def load_tree():
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_target_order_is_wp1_then_wp2_then_wp3():
    tree = load_tree()
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TARGETS"
            for target in node.targets
        )
    )

    assert [
        element.value for element in assignment.value.elts
    ] == ["WP1", "WP2", "WP3"]


def test_later_target_is_not_requested_after_failure():
    source = SOURCE.read_text(encoding="utf-8")

    assert "if not node.run_target(" in source
    assert "later targets were not requested" in source


def test_runner_disables_base_in_finally_block():
    tree = load_tree()
    main_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    try_node = next(
        node for node in ast.walk(main_function)
        if isinstance(node, ast.Try)
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "disable_base"
        for statement in try_node.finalbody
        for node in ast.walk(statement)
    )


def test_runner_maintains_enable_during_active_test():
    source = SOURCE.read_text(encoding="utf-8")

    assert 'self.create_timer(0.50, self._publish_enable_state)' in source
    assert "node.wait_for_navigation_command_path()" in source
    assert "command_topic:=/cmd_vel" in source
    assert "node.wait_for_enable_subscription()" in source
    assert "node.enable_base()" in source


def test_runner_exits_nonzero_on_failure():
    source = SOURCE.read_text(encoding="utf-8")

    assert "def main(args=None) -> int:" in source
    assert "return 1" in source
    assert "raise SystemExit(main())" in source

import ast
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "motivon_navigation"
    / "navigation_node.py"
)


def test_action_execution_does_not_require_an_asyncio_event_loop():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    navigation_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NavigationNode"
    )
    execute_goal = next(
        node
        for node in navigation_class.body
        if node.name == "_execute_goal"
    )

    assert isinstance(execute_goal, ast.FunctionDef)


def test_path_start_uses_configured_route_yaw():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    navigation_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NavigationNode"
    )
    start_path = next(
        node
        for node in navigation_class.body
        if node.name == "_start_path"
    )
    assignments = [
        node
        for node in ast.walk(start_path)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and target.attr == "active_travel_yaw"
            for target in node.targets
        )
    ]

    assert len(assignments) == 1
    value = assignments[0].value
    assert isinstance(value, ast.Attribute)
    assert isinstance(value.value, ast.Name)
    assert value.value.id == "path"
    assert value.attr == "travel_yaw"


def test_starting_a_path_does_not_redefine_the_verified_home_transform():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    navigation_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NavigationNode"
    )
    start_path = next(
        node
        for node in navigation_class.body
        if node.name == "_start_path"
    )

    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HomeTransform"
        for node in ast.walk(start_path)
    )


def test_shutdown_checks_the_ros_context_before_publishing_stop():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    navigation_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "NavigationNode"
    )
    destroy_node = next(
        node
        for node in navigation_class.body
        if node.name == "destroy_node"
    )

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "ok"
        for node in ast.walk(destroy_node)
    )

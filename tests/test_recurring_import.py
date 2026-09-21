import importlib
import inspect


PAGE_DEPENDENCIES = (
    "create_recurring",
    "list_occurrences",
    "list_recurring",
    "occurrence_status",
    "pay_occurrence",
    "set_recurring_status",
    "update_recurring",
)


def test_recurring_page_dependencies_are_importable():
    recurring = importlib.import_module("src.recurring")

    for name in PAGE_DEPENDENCIES:
        function = getattr(recurring, name, None)
        assert callable(function), f"src.recurring.{name} não está disponível"

    assert "status" in inspect.signature(recurring.list_recurring).parameters
    assert "database_path" in inspect.signature(recurring.list_occurrences).parameters

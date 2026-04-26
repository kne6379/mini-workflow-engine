import pytest

from workflow_engine.domain.errors import InputMappingError
from workflow_engine.nodes.prompts import render_template


def test_render_template_replaces_single_placeholder():
    result = render_template("Hello {{ name }}!", {"name": "Alice"})
    assert result == "Hello Alice!"


def test_render_template_handles_nested_path():
    result = render_template(
        "Plan: {{ customer.plan }}",
        {"customer": {"plan": "Enterprise"}},
    )
    assert result == "Plan: Enterprise"


def test_render_template_replaces_multiple_occurrences():
    result = render_template("{{ x }} and {{ x }}", {"x": "yes"})
    assert result == "yes and yes"


def test_render_template_raises_on_missing_path():
    with pytest.raises(InputMappingError):
        render_template("Hello {{ unknown }}!", {})


def test_render_template_coerces_sole_placeholder_to_str():
    result = render_template("{{ count }}", {"count": 3})
    assert isinstance(result, str)
    assert result == "3"

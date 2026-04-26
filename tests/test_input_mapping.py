import pytest

from workflow_engine.errors import InputMappingError
from workflow_engine.engine.input_mapping import render_inputs


def test_render_inputs_resolves_full_value_templates():
    context = {
        "input": {"inquiry_id": "INQ-002"},
        "nodes": {
            "fetch_inquiry": {
                "inquiry": {
                    "from": "minsu.kim@example.com",
                    "subject": "카드 결제가 계속 실패합니다",
                }
            }
        },
    }

    rendered = render_inputs(
        {
            "inquiry_id": "{{ input.inquiry_id }}",
            "email": "{{ nodes.fetch_inquiry.inquiry.from }}",
        },
        context,
    )

    assert rendered == {
        "inquiry_id": "INQ-002",
        "email": "minsu.kim@example.com",
    }


def test_render_inputs_resolves_embedded_templates():
    context = {
        "input": {},
        "nodes": {
            "fetch_inquiry": {
                "inquiry": {
                    "subject": "카드 결제가 계속 실패합니다",
                }
            }
        },
    }

    rendered = render_inputs(
        {"subject": "Re: {{ nodes.fetch_inquiry.inquiry.subject }}"},
        context,
    )

    assert rendered == {"subject": "Re: 카드 결제가 계속 실패합니다"}


def test_render_inputs_does_not_render_template_syntax_from_resolved_values():
    context = {
        "input": {
            "prefix": "{{ input.other }}",
            "other": "resolved",
        },
        "nodes": {},
    }

    rendered = render_inputs(
        {"subject": "{{ input.prefix }} / {{ input.other }}"},
        context,
    )

    assert rendered == {"subject": "{{ input.other }} / resolved"}


def test_render_inputs_resolves_nested_dicts_and_lists():
    context = {
        "input": {"inquiry_id": "INQ-002"},
        "nodes": {
            "fetch_inquiry": {
                "inquiry": {
                    "subject": "카드 결제가 계속 실패합니다",
                }
            }
        },
    }

    rendered = render_inputs(
        {
            "metadata": {
                "ids": ["{{ input.inquiry_id }}"],
                "subject": "Re: {{ nodes.fetch_inquiry.inquiry.subject }}",
            }
        },
        context,
    )

    assert rendered == {
        "metadata": {
            "ids": ["INQ-002"],
            "subject": "Re: 카드 결제가 계속 실패합니다",
        }
    }


def test_render_inputs_fails_when_path_is_missing():
    with pytest.raises(InputMappingError, match="nodes.fetch_inquiry.inquiry.from"):
        render_inputs({"email": "{{ nodes.fetch_inquiry.inquiry.from }}"}, {"input": {}, "nodes": {}})

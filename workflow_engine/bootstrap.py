from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflow_engine.adapters.fake_ai import FakeAI
from workflow_engine.adapters.mock_api import FakeMockAPIAdapter, MockAPIAdapter
from workflow_engine.adapters.openai import OpenAIAdapter
from workflow_engine.adapters.run_store import RunStoreAdapter
from workflow_engine.config import Settings
from workflow_engine.engine.executor import WorkflowExecutor
from workflow_engine.engine.registries import AITaskRegistry, ToolRegistry
from workflow_engine.engine.retry import RetryPolicy
from workflow_engine.nodes.llm import classify_email, generate_reply
from workflow_engine.nodes.tools import CRMLookupTool, EmailSendTool, InquiryGetTool


@dataclass
class AppDependencies:
    executor: WorkflowExecutor
    store: RunStoreAdapter
    workflow_paths: dict[str, Path]


def build_dependencies(settings: Settings) -> AppDependencies:
    """운영 의존성 조립."""
    store = RunStoreAdapter()
    mock_api = MockAPIAdapter(settings.mock_api_base_url, settings.mock_api_key)
    classify_ai = OpenAIAdapter(
        settings.openai_api_key, settings.classify_model, settings.openai_temperature,
    )
    generate_ai = OpenAIAdapter(
        settings.openai_api_key, settings.generate_model, settings.openai_temperature,
    )
    return _assemble(
        store=store,
        mock_api=mock_api,
        classify_ai=classify_ai,
        generate_ai=generate_ai,
    )


def build_test_dependencies(
    *,
    classify_response: dict[str, Any] | None = None,
    generate_response: dict[str, Any] | None = None,
    fake_mock_api: Any = None,
) -> AppDependencies:
    """테스트용 fake 의존성 조립."""
    store = RunStoreAdapter()
    mock_api = fake_mock_api or FakeMockAPIAdapter()
    classify_ai = FakeAI(classify_response if classify_response is not None else {"category": "billing"})
    generate_ai = FakeAI(generate_response if generate_response is not None else {
        "subject": "Re: 카드 결제가 계속 실패합니다",
        "body": (
            "안녕하세요. 결제 오류 문의 확인했습니다. "
            "예상 처리 기한 3영업일 이내, 접수 확인 번호 ACK-001입니다."
        ),
    })
    return _assemble(
        store=store,
        mock_api=mock_api,
        classify_ai=classify_ai,
        generate_ai=generate_ai,
        default_retry_policy=RetryPolicy(
            initial_delay_seconds=0, multiplier=1.0, max_delay_seconds=0,
        ),
    )


def _assemble(
    *, store, mock_api, classify_ai, generate_ai,
    default_retry_policy: RetryPolicy | None = None,
) -> AppDependencies:
    from workflow_engine.engine.approval_timer import ApprovalTimer

    tool_registry = ToolRegistry({
        "inquiry_get": InquiryGetTool(mock_api),
        "crm_lookup": CRMLookupTool(mock_api),
        "email_send": EmailSendTool(mock_api),
    })
    ai_registry = AITaskRegistry(
        tasks={"classify_email": classify_email, "generate_reply": generate_reply},
        profiles={"classify_email": classify_ai, "generate_reply": generate_ai},
    )
    timer = ApprovalTimer()
    executor = WorkflowExecutor(
        store=store,
        tool_registry=tool_registry,
        ai_registry=ai_registry,
        approval_timer=timer,
        default_retry_policy=default_retry_policy,
    )
    timer.set_on_expire(executor.expire_run)
    return AppDependencies(
        executor=executor,
        store=store,
        workflow_paths={
            "customer_support_auto_reply": Path("workflows/customer_support_auto_reply.yaml"),
        },
    )

CATEGORIES = ["billing", "technical", "account", "feature_request", "general"]

CATEGORY_GUIDELINES = {
    "billing": "빠른 확인과 처리 약속, 우선 전달. 환불/중복결제는 3영업일 이내 처리.",
    "technical": "문제 인지 여부와 조사 상태 명확히 전달. 임시 해결책 함께 안내.",
    "account": "보안 확인 절차 안내. 비밀번호 재설정은 단계별 가이드 제공.",
    "feature_request": "피드백 감사 표현. 로드맵 반영 여부와 대안 기능 안내.",
    "general": "요청 사항 파악 후 적절한 부서/리소스로 안내.",
}

PLAN_RULES = {
    "Enterprise": "전담 매니저/엔지니어 연결 안내, 우선 처리 강조, SSO 전담 지원, 제품팀 직접 미팅 제안 가능.",
    "Business": "일반 지원 채널 안내, 기술 지원 티켓 순차 처리, 셀프서비스 가이드 우선 제공.",
    "Free": "커뮤니티/공식문서 우선 안내, 유료 플랜 전환 혜택 함께 안내, 기본 기능만 지원됨을 명시.",
}

REQUIRED_INCLUDES = {
    "billing": ["예상 처리 기한", "접수 확인 번호"],
    "technical": ["문제 인지 여부", "예상 해결 일정"],
    "account": ["보안 절차 안내", "예상 처리 시간"],
    "feature_request": ["피드백 감사", "검토 예정 안내"],
    "general": [],
}

CATEGORY_TONE = {
    "billing": "정중하고 신속",
    "technical": "전문적이고 체계적",
    "account": "보안을 강조하며 친절",
    "feature_request": "감사와 공감",
    "general": "친근하고 도움이 되는",
}

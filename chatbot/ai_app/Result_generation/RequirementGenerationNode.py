# ai_app/Result_generation/RequirementsNode.py
import logging
from data.data_models import AgentState, WritingRequirements
from ai_app.assist.common import writing_requirements_manager  # 인스턴스 참조

logger = logging.getLogger(__name__)

def requirements_node(state: AgentState) -> AgentState:
    """
    WritingRequirementsManager에서 요구사항을 불러와 state에 저장하는 노드.
    """
    logger.info("🧠 RequirementsNode 실행 시작")

    try:
        # 외부 저장된 요구사항 불러오기 (dict 형태)
        raw_requirements = writing_requirements_manager.get_requirements()
        state.requirements = WritingRequirements(**raw_requirements)
        state.current_operation_step = "요구사항 불러오기 완료"
        logger.info("✅ 요구사항 복원 및 상태 저장 완료")
    except Exception as e:
        logger.exception("❌ 요구사항 복원 실패")
        state.error_message = f"RequirementsNode 오류: {e}"

    return state

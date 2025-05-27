import json
from fastapi import FastAPI, HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ai_app.chatbot import Chatbot  # 기존 코드의 Chatbot 클래스 임포트
from ai_app.chatbotStream import ChatbotStream
from ai_app.assist.common import client, model
from fastapi.responses import StreamingResponse
import asyncio
from ai_app.assist.characters import instruction,system_role
from ai_app.utils.function_calling import FunctionCalling, tools # 단일 함수 호출
from contextlib import asynccontextmanager
from ai_app.utils.auto_summary import router as memory_router # 추가
from ai_app.utils.auto_summary import get_auto_summary
'''
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시에는 별다른 동작 없이 바로 yield
    yield
    # 종료 시 실행할 코드
    print("FastAPI shutting down...")
    chatbot.save_chat()
    print("Saved!")'''

#app = FastAPI(lifespan)
#몽고디비 저장 비활성화 주석
app = FastAPI()
app.include_router(memory_router) #추가 - auto_summary.py에 정의된 별도의 API 기능들(예: 요약 조회, 저장 등)을 main 서버에 연결해주는 장치
'''chatbot = Chatbot(
    model=model.basic,
    system_role = system_role,
    instruction=instruction,
    user= "대기",
    assistant= "memmo"
    )  # 모델 초기화'''

chatbot=ChatbotStream(
    model=model.advanced,
    system_role = system_role,
    instruction=instruction,
    user= "대기",
    assistant= "memmo"
    )
# CORS 설정 (안드로이드 앱 접근 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
''' FastAPI는 Pydantic을 기본적으로 지원

FastAPI에서는 요청 데이터를 받을 때, request.json을 직접 쓰지 않고 Pydantic 모델을 매개변수로 넣으면 자동으로 처리해 줘요.
-Flask에서는 직접 Pydantic을 호출해야 함
Flask는 기본적으로 Pydantic을 지원하지 않기 때문에, request.json을 가져와서 Pydantic 모델로 수동으로 검증해야 해요.'''
class UserRequest(BaseModel):
    message: str

def update_field_bound(field_name: str, new_content: str):
    return chatbot.writingRequirementsManager.update_field(field_name, new_content)

# tools 목록에서 해당 이름으로 매칭되도록 래핑한 함수 등록
func_calling = FunctionCalling(
    model=model.basic,
    available_functions={
        "update_field": update_field_bound,
        # 필요시 다른 함수도 여기에 추가
    }
)
@app.post("/stream-chat")
async def stream_chat(user_input: UserRequest):
    """
    사용자 메시지를 처리하여 챗봇과 대화한다.
    현재 방에 문맥에 따라 문맥을 교체 하며 대화.
    
    Args:
        user_input (UserRequest): 사용자가 입력한 메시지.
    
    Returns:
        StreamingResponse: GPT 스트리밍 응답 또는 요약/제목 JSON.
    """
   # 1) 사용자 메시지를 원본 문맥에 그대로 추가
    chatbot.add_user_message_in_context(user_input.message)
    # 1-1) MongoDB에 저장
    chatbot.save_chat()
    # 2) 현재 대화방 문맥 가져오기 및 API 형식 변환
    current_context = chatbot.get_current_context()
    temp_context = chatbot.to_openai_context(current_context).copy()
    # ✅ [② AutoSummary fallback 판단 및 실행] 
    auto_summary = get_auto_summary()
    
    # 메모리 체크 결과를 받지만, 원본 사용자 메시지를 유지합니다
    memory_data = auto_summary.answer_with_memory_check(user_input.message, temp_context)
    
    if chatbot.current_field != "main":
        instruction = chatbot.field_instructions.get(chatbot.current_field, chatbot.instruction)
        # 마지막 사용자 메시지에 지침 추가
        for msg in reversed(temp_context):
            if msg["role"] == "user":
                msg["content"] = f"{msg['content']}\ninstruction: {instruction}"
                break
    print("함수호출 시작작")
    # 메모리에서 관련 정보가 발견되면, 컨텍스트에 추가 정보로 포함시킵니다
    if memory_data and memory_data != user_input.message:
        # 기존 컨텍스트를 유지하면서 메모리 정보를 추가
        temp_context.append({
            "role": "system", 
            "content": f"다음은 사용자 질문과 관련된 기존 대화 기록입니다: {memory_data}"
        })
    
    # 함수 호출 분석은 항상 원본 컨텍스트(사용자 메시지 포함)로 수행
    print("함수호출 시작")
    analyzed = func_calling.analyze(user_input.message, tools)  # memory_response 대신 원본 메시지 사용

    for tool_call in analyzed:  # analyzed는 list of function_call dicts
            if tool_call.type != "function_call":
                continue
            func_name = tool_call.name
            func_args = json.loads(tool_call.arguments)
            call_id = tool_call.call_id

            func_to_call = func_calling.available_functions.get(func_name)
            if not func_to_call:
                print(f"[오류] 등록되지 않은 함수: {func_name}")
                continue

            try:
               
                function_call_msg = {
                    "type": "function_call",  # 고정
                    "call_id": call_id,  # 딕셔너리 내에 있거나 key가 다를 수 있으니 주의
                    "name": func_name,
                    "arguments": tool_call.arguments  # dict -> JSON string
                }
                print(f"함수 호출 메시지: {function_call_msg}")
                if func_name == "search_internet":
                    # context는 이미 run 메서드의 매개변수로 받고 있음
                   func_response = func_to_call(chat_context=current_context[:], **func_args)
                else:
                   func_response = func_to_call(**func_args)

                temp_context.extend([
                    function_call_msg,
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": str(func_response)
                }
            ])
                print(temp_context)

            except Exception as e:
                print(f"[함수 실행 오류] {func_name}: {e}")

    # 4) 함수 호출 결과가 반영된 temp_context으로 스트리밍 응답을 생성
    async def generate_with_tool():
        try:
            # stream=True로 스트리밍 응답
            stream = client.responses.create(
            model=chatbot.model,
            input=temp_context,  # user/assistant 역할 포함된 list 구조
            top_p=1,
            stream=True,
            text={
                "format": {
                    "type": "text"  # 또는 "json_object" 등 (Structured Output 사용 시)
                }
            }
                )
              
            loading = True
            for event in stream:
                        match event.type:
                            case "response.created":
                                print("[🤖 응답 생성 시작]")
                                loading = True
                                # 로딩 애니메이션용 대기 시작
                                yield "⏳ GPT가 응답을 준비 중입니다..."
                                await asyncio.sleep(0)
                            case "response.output_text.delta":
                                if loading:
                                    print("\n[💬 응답 시작됨 ↓]")

                                    loading = False
                                # 글자 단위 출력
                                yield f"{event.delta}"
                                await asyncio.sleep(0)
                            

                            case "response.in_progress":
                                print("[🌀 응답 생성 중...]")
                                yield "[🌀 응답 생성 중...]"
                                yield "\n"

                            case "response.output_item.added":
                                if getattr(event.item, "type", None) == "reasoning":
                                    yield "[🧠 GPT가 추론을 시작합니다...]"
                                    yield "\n"
                                elif getattr(event.item, "type", None) == "message":
                                    yield "[📩 메시지 아이템 추가됨]"
                                    yield "\n"
                            #ResponseOutputItemDoneEvent는 우리가 case "response.output_item.done"에서 잡아야 해
                            case "response.output_item.done":
                                item = event.item
                                if item.type == "message" and item.role == "assistant":
                                    for part in item.content:
                                        if getattr(part, "type", None) == "output_text":
                                            completed_text= part.text
                            case "response.completed":
                                yield "\n"
                                chatbot.add_response_stream(completed_text)
                                print(f"\n📦 스트림 완료 출력: \n{completed_text}")
                            case "response.failed":
                                print("❌ 응답 생성 실패")
                                yield "❌ 응답 생성 실패"
                            case "error":
                                print("⚠️ 스트리밍 중 에러 발생!")
                                yield "⚠️ 스트리밍 중 에러 발생!"
                            case _:
                                yield "\n"
                                yield f"[📬 기타 이벤트 감지: {event.type}]"
        except Exception as e:
            yield f"\nStream Error: {str(e)}"

    return StreamingResponse(generate_with_tool(), media_type="text/plain")

@app.post("/enter-sub-conversation/{field_name}")
async def enter_sub_conversation(field_name: str):
    """
    지정된 서브 대화방으로 전환.
    
    Args:
        field_name (str): 전환할 서브 대화방 이름.
    
    Returns:
        dict: 전환 성공 메시지.
    """
    valid_fields = [
        "purpose_background", "context_topic", "audience_scope", "format_structure",
        "logic_evidence", "expression_method", "additional_constraints", "output_expectations"
    ]
    if field_name not in valid_fields:
        raise HTTPException(status_code=400, detail="유효하지 않은 서브 대화방입니다.")
    message = chatbot.enter_sub_conversation(field_name)
    return {"message": message}
@app.post("/exit-conversation")
async def exit_conversation():
    """
    현재 서브 대화방을 종료하고 메인 대화방으로 복귀
    
    Returns:
        dict: 종료 메시지.
    """
    message = chatbot.exit_sub_conversation()
    return {"message": message}



@app.get("/current-conversation")
async def get_current_conversation():
    """
    현재 대화방 상태를 반환.
    
    Returns:
        dict: 현재 대화방 이름과 상태 메시지를 포함한 JSON 응답.
    """
    current_field = chatbot.current_field
    if current_field == "main":
        message = "현재 메인 대화방에 있습니다."
    else:
        message = f"현재 {current_field} 서브 대화방에 있습니다."
    
    return {
        "success": True,
        "current_field": current_field,
        "message": message
    }

@app.get("/conversation-history/{field_name}")
async def get_conversation_history(field_name: str):
    """
    지정된 대화방의 대화 기록을 반환합니다.
    
    Args:
        field_name (str): 대화방 이름 (main 또는 서브 대화방).
    
    Returns:
        dict: 대화 기록과 상태 메시지를 포함한 JSON 응답.
    """
    valid_fields = [
        "main", "purpose_background", "context_topic", "audience_scope", "format_structure",
        "logic_evidence", "expression_method", "additional_constraints", "output_expectations"
    ]
    if field_name not in valid_fields:
        raise HTTPException(status_code=400, detail="유효하지 않은 대화방입니다.")
    
    if field_name == "main":
        history = chatbot.context
    else:
        history = chatbot.sub_contexts.get(field_name, {}).get("messages", [])
    
    return {
        "success": True,
        "field_name": field_name,
        "history": history,
        "message": f"{field_name} 대화방의 기록을 반환했습니다."
    }

@app.post("/reset-conversation")
async def reset_conversation():
    """
    대화 상태를 초기화합니다.
    
    Returns:
        dict: 초기화 성공 메시지를 포함한 JSON 응답.
    """
    chatbot.context = [{"role": "system", "content": system_role}]  # 메인 문맥 초기화
    chatbot.sub_contexts = {}  # 서브 문맥 초기화
    chatbot.current_field = "main"  # 대화방 상태 초기화
    return {
        "success": True,
        "message": "대화 상태가 초기화되었습니다."
    }
@app.get("/field-content/{field_name}")
async def get_field_content(field_name: str):
    """
    지정된 필드의 내용을 반환합니다.
    
    Args:
        field_name (str): 조회할 필드 이름.
    
    Returns:
        dict: 필드 내용과 상태 메시지를 포함한 JSON 응답.
    """
    valid_fields = [
        "purpose_background", "context_topic", "audience_scope", "format_structure",
        "logic_evidence", "expression_method", "additional_constraints", "output_expectations"
    ]
    if field_name not in valid_fields:
        raise HTTPException(status_code=400, detail="유효하지 않은 필드입니다.")
    
    print(f"DEBUG: WritingRequirementsManager 인스턴스 ID: {chatbot.writingRequirementsManager}")
    print(f"DEBUG: 현재 모든 필드: {chatbot.writingRequirementsManager.writing_requirements}")
    content = chatbot.writingRequirementsManager.get_field_content(field_name)
    print(f"DEBUG: 요청된 필드 '{field_name}' 내용: {content}")
    return {
        "success": True,
        "field_name": field_name,
        "content": content,
        "message": f"{field_name} 필드의 내용을 반환했습니다."
    }
class UpdateFieldRequest(BaseModel):
    field_name: str
    content: str
    
@app.post("/update-field")
async def update_field(request: UpdateFieldRequest):
    """
    지정된 필드의 내용을 업데이트하고, 요약 및 clarification_question을 생성합니다.
    
    Args:
        request (UpdateFieldRequest): 필드 이름과 새로운 내용.
    
    Returns:
        dict: 업데이트 결과, 요약, clarification_question을 포함한 JSON 응답.
    """
    valid_fields = [
        "purpose_background", "context_topic", "audience_scope", "format_structure",
        "logic_evidence", "expression_method", "additional_constraints", "output_expectations"
    ]
    if request.field_name not in valid_fields:
        raise HTTPException(status_code=400, detail="유효하지 않은 필드입니다.")
    
    # 필드 업데이트
    update_message = chatbot.writingRequirementsManager.update_field(request.field_name, request.content)
    print(f"DEBUG: 필드 '{request.field_name}' 업데이트 메시지: {update_message}")
    # Clarification Question 생성
    try:
        response = client.responses.create(
            model=chatbot.model,
            input=[{
                "role": "user",
                "content": f"다음 필드 내용에 기반하여 관련된 질문을 생성하세요:\n{request.content}"
            }],
        )
        question = response.output_text
        if request.field_name in chatbot.sub_contexts:
            chatbot.sub_contexts[request.field_name]["clarification_question"] = question
    except Exception as e:
        question = ""
        print(f"Clarification question 생성 오류: {e}")
    
    return {
        "success": True,
        "field_name": request.field_name,
        "content": chatbot.writingRequirementsManager.get_field_content(request.field_name),
        "clarification_question": question,
        "message": update_message
    }

@app.post("/generate-document")
async def generate_document():
    """
    WritingRequirementsManager에 저장된 현재 요구사항을 기반으로
    LangGraph 파이프라인을 실행하여 최종 결과물을 생성합니다.
    """
    try:
        from data.data_models import AgentState, WritingRequirements
        from ai_app.Result_generation.nodes import run_pipeline
        # --- 여기가 바로 우리가 논의한 '데이터 연결' 로직입니다 ---

        # 1. 관리자로부터 실시간 요구사항 데이터를 딕셔너리로 가져오기
        requirements_dict = chatbot.writingRequirementsManager.get_requirements()
        print(f"DEBUG: Manager에서 가져온 요구사항: {requirements_dict}")

        # 2. 딕셔너리를 WritingRequirements 모델 객체로 변환하기
        requirements_model = WritingRequirements(**requirements_dict)

        # 3. 모델 객체를 사용하여 AgentState의 초기 상태를 생성하기
        initial_state = AgentState(requirements=requirements_model)

        # 4. 실제 데이터가 담긴 상태로 LangGraph 파이프라인 실행하기
        print("INFO: LangGraph 파이프라인 실행을 시작합니다.")
        final_state = run_pipeline(initial_state)
        print("INFO: LangGraph 파이프라인 실행이 완료되었습니다.")

        # 5. 최종 결과물을 추출하여 클라이언트에게 반환하기
        final_output = final_state.get("final_iteration_output", {})
        if not final_output:
            error_msg = final_state.get("error_message", "알 수 없는 오류가 발생했습니다.")
            raise HTTPException(status_code=500, detail=f"결과 생성 실패: {error_msg}")

        # 딕셔너리에서 'final_text' 키의 값을 직접 추출합니다.
        final_text = final_output.get("final_text", "오류: 최종 결과물을 찾을 수 없습니다.")

        # 클라이언트가 가장 필요로 하는 'final_text'를 최상위 레벨로 반환합니다.
        return {"success": True, "final_text": final_text}

    except Exception as e:
        # 기타 예외 처리
        print(f"ERROR: /generate-document 엔드포인트에서 예외 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))
import json
from fastapi import FastAPI, HTTPException,Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ai_app.chatbot import Chatbot  # 기존 코드의 Chatbot 클래스 임포트
from ai_app.chatbotStream import ChatbotStream
from ai_app.common import client, model
from fastapi.responses import StreamingResponse
import asyncio
from ai_app.characters import instruction,system_role
from ai_app.utils.function_calling import FunctionCalling, tools # 단일 함수 호출
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시에는 별다른 동작 없이 바로 yield
    yield
    # 종료 시 실행할 코드
    print("FastAPI shutting down...")
    chatbot.save_chat()
    print("Saved!")


app = FastAPI(lifespan=lifespan)
'''chatbot = Chatbot(
    model=model.basic,
    system_role = system_role,
    instruction=instruction,
    user= "대기",
    assistant= "memmo"
    )  # 모델 초기화'''

chatbot=ChatbotStream(
    model=model.basic,
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

func_calling = FunctionCalling(model=model.basic)


@app.post("/stream-chat")
async def stream_chat(user_input: UserRequest):
    # 1) 사용자 메시지를 우선 원본 문맥에 추가
    chatbot.add_user_message_in_context(user_input.message)
    
    # 추가 지시사항(기존 코드에 있던 부분)
    chatbot.context[-1]['content'] += chatbot.instruction

    # 2) 사용자 입력을 분석해 함수 호출이 필요한지 확인
    # -- 여기서 새로 추가된 부분 --
    analyzed, analyzed_dict = func_calling.analyze(user_input.message, tools)

    # 3) 함수 호출(툴 실행)이 있는지 확인
    if analyzed_dict.get("tool_calls"):
        # 함수 호출이 있다면 임시문맥을 생성
        temp_context=chatbot.to_openai_context()[:]
        temp_context.append(analyzed)      # 분석된 메시지를 임시문맥에 추가
        tool_calls = analyzed_dict['tool_calls']

        for tool_call in tool_calls:
            function = tool_call["function"]
            func_name = function["name"]
            func_to_call = func_calling.available_functions[func_name]

            try:
                # 함수 인자 파싱
                func_args = json.loads(function["arguments"])
                # 실제 함수 호출
                func_response = func_to_call(**func_args)
                temp_context.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": func_name,
                    "content": str(func_response)
                })#실행 결과를 문맥에 추가
            except Exception as e:
                # 함수 실행 중 에러 처리
                error_msg = f"[함수 실행 오류] {str(e)}"
                # 원하는 방식으로 로그 남기거나 스트리밍 반환 가능
                temp_context.append({
                    "role": "assistant",
                    "content": error_msg
                })

        # 4) 함수 호출 결과가 반영된 임시 문맥으로 스트리밍 응답을 생성
        async def generate_with_tool():
            collected_text = ""
            try:
                # stream=True로 스트리밍 응답
                response = client.chat.completions.create(
                    model=chatbot.model,
                    messages=temp_context,
                    temperature=0.5,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream=True
                )
                for chunk in response:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            text_piece = delta.content
                            yield f"{text_piece}"
                            await asyncio.sleep(0)
                            collected_text += text_piece
            except Exception as e:
                yield f"\nStream Error: {str(e)}"
            finally:
                # 스트리밍이 끝나면 최종 응답을 원본 문맥에만 반영하고 임시문맥은 사용하지 않음
                               # 기존 clean 방식 유지
                chatbot.add_response_stream(collected_text)
                
                          # 최종 응답을 원본 문맥에 저장
        # 5) 함수 호출이 있을 때는 위의 generate_with_tool()를 사용
        return StreamingResponse(generate_with_tool(), media_type="text/plain")

    else:
        # 함수 호출이 없는 경우, 기존 로직대로 스트리밍 처리
        async def generate():
            collected_text = ""
            try:
                response = client.chat.completions.create(
                    model=chatbot.model,
                    messages=chatbot.to_openai_context(),
                    temperature=0.5,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream=True
                )
                for chunk in response:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            text_piece = delta.content
                            yield f"{text_piece}"
                            await asyncio.sleep(0)
                            collected_text += text_piece
            except Exception as e:
                yield f"\nStream Error: {str(e)}"
            finally:
                
                chatbot.add_response_stream(collected_text)
                chatbot.clean_context()
                print(chatbot.context)

        # 함수 호출이 없을 때는 기존 generate() 사용
        return StreamingResponse(generate(), media_type="text/plain")

@app.post("/completion-chat")
async def chat_api(request_data: UserRequest):
    ''' FastAPI의 request_data는 Pydantic 모델 객체라서 .(점)으로 접근 가능
FastAPI에서는 요청 데이터를 받을 때, Pydantic 모델(UserRequest)을 사용해 JSON 데이터를 Python 객체로 변환해 줘요.
즉, request_data는 그냥 dict가 아니라 클래스 객체처럼 동작하는 Pydantic 인스턴스가 돼요!

💡 FastAPI에서는 request_data가 Pydantic 모델 객체이므로 request_data.request_message처럼 멤버 변수로 접근할 수 있음.'''
    request_message = request_data.request_message
    print("request_message:", request_message)
    chatbot.add_user_message_in_context(request_message)

    
    # 챗GPT에게 함수사양을 토대로 사용자 메시지에 호응하는 함수 정보를 분석해달라고 요청
    analyzed_dict=func_calling.analyze(request_message,tools)
    # 챗GPT가 함수 호출이 필요하다고 분석했는지 여부 체크
    if analyzed_dict.get("function_call"): # 단일 함수 호출
        response = func_calling.run( analyzed_dict, chatbot.context[:]) # 단일 함수 호출
        chatbot.add_response(response)
    else:
        response = chatbot.send_request()#instructoin추가
        chatbot.add_response(response)

    response_message = chatbot.get_response()
    chatbot.clean_context()#instructoin제거
    print("response_message:", response_message)
    return {"response_message": response_message}




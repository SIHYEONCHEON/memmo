import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import json
from ai_app.common import client, model,makeup_response
from ai_app.characters import instruction,system_role
import math
from ai_app.utils.function_calling import FunctionCalling,tools
from db.memory_manager import MemoryManager

# 2025년 표준 API 지침 준수: 
# - POST /v1/chat/completions
# - body: { model: "gpt-...", input: [...] }
# - 인증: "Authorization: Bearer YOUR_API_KEY"


class ChatbotStream:
    def __init__(self, model,system_role,instruction,**kwargs):
        """
        초기화:
          - context 리스트 생성 및 시스템 역할 설정
          - openai.api_key 설정
          - 사용할 모델명 저장
          - 사용자 이름
          - assistant 이름름
        """
        self.context = [{"role": "system","content": system_role}]
        self.model = model
        self.instruction=instruction

        self.max_token_size = 16 * 1024 #최대 토큰이상을 쓰면 오류가발생 따라서 토큰 용량관리가 필요.
        self.available_token_rate = 0.9#최대토큰의 90%만 쓰겠다.
    
        self.username=kwargs["user"]
        self.assistantname=kwargs["assistant"]
        self.memoryManager = MemoryManager()
       
    def add_user_message_in_context(self, message: str):
        """
        사용자 메시지 추가:
          - 사용자가 입력한 message를 context에 user 역할로 추가
        """
        self.context.append({
            "role": "user",
            "content": message,
            "saved" : False
            })
#전송부
    def _send_request_Stream(self,temp_context=None):
        if temp_context is None:
           stream = client.responses.create(
            model=self.model,
            input=self.to_openai_context(),  # user/assistant 역할 포함된 list 구조
            
            top_p=1,
            stream=True,
            # Responses API에 맞는 추가 구성 예시 (선택 사항)
            
            text={
                "format": {
                    "type": "text"  # 또는 "json_object" 등 (Structured Output 사용 시)
                }
            }
                )
        else:  
           stream = client.responses.create(
            model=self.model,
            input=self.to_openai_context(),  # user/assistant 역할 포함된 list 구조
            top_p=1,
            stream=True,
            text={
                "format": {
                    "type": "text"  # 또는 "json_object" 등 (Structured Output 사용 시)
                }
            }
                )
              
        loading = True  # delta가 나오기 전까지 로딩 중 상태 유지       
        for event in stream:
            match event.type:
                case "response.created":
                    print("[🤖 응답 생성 시작]")
                    loading = True
                    # 로딩 애니메이션용 대기 시작
                    print("⏳ GPT가 응답을 준비 중입니다...")
                case "response.output_text.delta":
                    if loading:
                        print("\n[💬 응답 시작됨 ↓]")
                        loading = False
                    # 글자 단위 출력
                    print(event.delta, end="", flush=True)
                 

                case "response.in_progress":
                    print("[🌀 응답 생성 중...]")

                case "response.output_item.added":
                    if getattr(event.item, "type", None) == "reasoning":
                        print("[🧠 GPT가 추론을 시작합니다...]")
                    elif getattr(event.item, "type", None) == "message":
                        print("[📩 메시지 아이템 추가됨]")
                #ResponseOutputItemDoneEvent는 우리가 case "response.output_item.done"에서 잡아야 해
                case "response.output_item.done":
                    item = event.item
                    if item.type == "message" and item.role == "assistant":
                        for part in item.content:
                            if getattr(part, "type", None) == "output_text":
                                completed_text= part.text
                case "response.completed":
                    print("\n")
                    #print(f"\n📦 최종 전체 출력: \n{completed_text}")
                case "response.failed":
                    print("❌ 응답 생성 실패")
                case "error":
                    print("⚠️ 스트리밍 중 에러 발생!")
                case _:
                    
                    print(f"[📬 기타 이벤트 감지: {event.type}]")
        return completed_text
  
        
    def send_request_Stream(self):
      self.context[-1]['content']+=self.instruction
      #context문 맨 마지막에 instruction을 추가해라.
      return self._send_request_Stream()#->실제 보내는 코드는 _send_request 이다,
    
    def add_response(self, response):
        response_message = {
            "role" : response['choices'][0]['message']["role"],
            "content" : response['choices'][0]['message']["content"],
            "saved" : False
        }
        self.context.append(response_message)

    def add_response_stream(self, response):
            self.context.append({
                    "role" : "assistant",
                    "content" : response,
                    "saved" : False,
                }
            )
    def get_response(self, response_text: str):
        """
        응답내용반환:
          - 메시지를 콘솔(또는 UI) 출력 후, 그대로 반환
        """
        print(response_text['choices'][0]['message']['content'])
        return response_text
    def clean_context(self):
        '''
        1.context리스트에 마지막 인덱스부터 처음까지 순회한다
        2."instruction:\n"을 기준으로 문자열을 나눈다..첫user을 찾으면 아래 과정을 진행한다,
        3.첫 번째 부분 [0]만 가져온다. (즉, "instruction:\n" 이전의 문자열만 남긴다.)
        4.strip()을 적용하여 앞뒤의 공백이나 개행 문자를 제거한다.
        '''
        for idx in reversed(range(len(self.context))):
            if self.context[idx]['role']=='user':
                self.context[idx]["content"]=self.context[idx]['content'].split('instruction:\n')[0].strip()
                break
    def handle_token_limit(self, response):
        # 누적 토큰 수가 임계점을 넘지 않도록 제어한다.
        try:
            current_usage_rate = response['usage']['total_tokens'] / self.max_token_size
            exceeded_token_rate = current_usage_rate - self.available_token_rate
            if exceeded_token_rate > 0:
                remove_size = math.ceil(len(self.context) / 10)
                self.context = [self.context[0]] + self.context[remove_size+1:]
        except Exception as e:
            print(f"handle_token_limit exception:{e}")
    def to_openai_context(self):
        return [{"role":v["role"], "content":v["content"]} for v in self.context]
    def save_chat(self):
        self.memoryManager.save_chat(self.context)   
 
if __name__ == "__main__":
    
    chatbot = ChatbotStream(
        model.advanced,
        system_role=system_role,
        instruction=instruction,
        user="대기",
        assistant="memmo")
    func_calling=FunctionCalling(model.advanced)
    print("===== Chatbot Started =====")
    print("초기 context:", chatbot.context)
    print("사용자가 'exit'라고 입력하면 종료합니다.\n")

    while True:
        user_input = input("User > ")
        if user_input.strip().lower() == "exit":
            print("Chatbot 종료.")
            break

        # 사용자 메시지를 문맥에 추가
        chatbot.add_user_message_in_context(user_input)

        # 사용자 입력 분석 (함수 호출 여부 확인)
        analyzed, analyzed_dict = func_calling.analyze(user_input, tools)

        if analyzed_dict.get("tool_calls"):
            
            # 도구 실행 및 결과를 문맥에 추가
            temp_context=chatbot.to_openai_context().copy()#chatbot.context[:]
            #temp_context=chatbot.context[:]
           
            temp_context.append(analyzed)
            tool_calls = analyzed_dict['tool_calls']

            print(analyzed)

            for tool_call in tool_calls:
                function=tool_call["function"]
                func_name=function["name"]
                func_to_call = func_calling.available_functions[func_name]
                try:
                    func_args=json.loads(function["arguments"])#딕셔너리로 변환-> 문자열이 json형태입-> 이걸 딕셔너리로 변환
                    func_response=func_to_call(**func_args)
                    temp_context.append({
                        "tool_call_id": tool_call["id"],
                        "role": "tool",
                        "name": func_name, 
                        "content": str(func_response)
                    })
                except Exception as e:
                    print("Error occurred(run):",e)
                    print(makeup_response("[run 오류입니다]"))
                # 스트리밍 출력으로 최종 응답 생성
            streamed_response = chatbot._send_request_Stream(temp_context=temp_context)
            temp_context=None
            chatbot.add_response_stream(streamed_response)  # 응답을 문맥에 추가
            print(chatbot.context)

            

            
        else:
            # 일반 대화 처리 (스트리밍 출력)
            streamed_response = chatbot.send_request_Stream()
            chatbot.clean_context()
            chatbot.add_response_stream(streamed_response)  # 응답을 문맥에 추가
            

            

    print("===== Chatbot Finished =====")
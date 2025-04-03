import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import json
from ai_app.common import client, model,makeup_response
from ai_app.characters import instruction,system_role
import math
from ai_app.utils.function_calling import FunctionCalling,tools
from db.memory_manager import MemoryManager
import copy
# 2025년 표준 API 지침 준수: 
# - POST /v1/chat/completions
# - body: { model: "gpt-...", messages: [...] }
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
        #self.context.extend(self.memoryManager.restore_chat())
#사용자의 입력을 맥락에에 추가
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
# _send,,,와 send 가 있다. 
# send_request_Steam은 사용자 응답에 지침을 더해 대답을 생성한다.
# _send는 단순 출력부로 현재 문맥에 따라 대답을 제공한다.
#이렇게 구분한이유는 에이전트 도구사용과 같은 동작에서는 사용자 지침보다,도구를 사용한 결과값이 중요하기떄문
#send는 기억 검색도 실시한다. 즉 사용자의 질문에 항상 기억검색 여부를 판단한다.
# 이처럼 _ send동작을 처리하기 전까지 해야되는 처리는 send에 둔다.
  
    def _send_request_Stream(self,temp_context=None):
        if temp_context is None:
            response = client.chat.completions.create(
                    model=self.model, 
                    messages=self.to_openai_context(),
                    temperature=0.5,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream=True
                )
        else:
            response = client.chat.completions.create(
            model=self.model, 
            messages=temp_context,
            temperature=0.5,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True
        )
                
        collected_text = ""
        
        for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:  
                    text_piece = delta.content
                    print(text_piece, end="", flush=True)
                    collected_text += text_piece
        print()

        return collected_text  # 완성된 전체 텍스트 반환 
      
    def send_request_Stream(self):
      memory_instruction = self.search_memory_inDB()
      self.context[-1]['content'] += self.instruction + (memory_instruction if memory_instruction else "")
      #context문 맨 마지막에 instruction을 추가해라.
      return self._send_request_Stream()#->실제 보내는 코드는 _send_request 이다.



    def send_request(self):
        memory_instruction = self.search_memory_inDB()
        self.context[-1]['content'] += self.instruction + (memory_instruction if memory_instruction else "")
       
    def search_memory_inDB(self):
        '''
        Context에 없는 내용을 사용자가 물으면 DB에서 검색한다.
        memoryManager.retrieve_memory()에서 사용자 질의로 벡터 검색을 해 몽고에서 데이터를 가져온다.
        검색 데이터가 없다면 NONE을 반환->이때 우리는 해당 기억이 없다는 내용을 자연스럽게 사용자에게 전달한다.
        '''
        
        #AI에게 보내기전, 문맥에서 마지막 사용자 메세지를 가져와 DB에 검색해야 되는지를 판단한다.
        user_message= self.context[-1]['content'] 
        if not self.memoryManager.needs_memory(user_message):#기억할 필요가 없다면 기억검색을 하지않는다.
            return
        else:
            memory = self.memoryManager.retrieve_memory(user_message) #검색한다, 검색결과가 있다면 기억이 들어가고 없거나 유사도가 낮다면 NONE을 반환한다
        
        if memory is not None:
            whisper = (
            f"[Whisper]\n{self.assistantname}, here’s a memory from a previous conversation. "
            f"Please use this as context when responding going forward. "
            f"Respond in a natural and conversational tone, like in our recent exchange:\n{memory}"
            )
            self.add_user_message_in_context(whisper)
        else:
            return "[If no memory exists, respond by saying you don’t remember.]"
       
#대화 문맥 추가*add response 수정-> 응답객체에서 content 추출출
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
    func_calling=FunctionCalling(model.basic)
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
            
            temp_context=copy.deepcopy(chatbot.to_openai_context())
            temp_context.append(analyzed)
            tool_calls = analyzed_dict['tool_calls']

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
            

            
        else:
            # 일반 대화 처리 (스트리밍 출력)
            streamed_response = chatbot.send_request_Stream()
            chatbot.clean_context()
            chatbot.add_response_stream(streamed_response)  # 응답을 문맥에 추가
            

            

    print("===== Chatbot Finished =====")
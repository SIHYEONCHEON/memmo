import json
from common import client, model,makeup_response
import sys
from characters import instruction,system_role
import math
from function_calling import FunctionCalling,tools
from memory_manager import MemoryManager

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
        """def handle_token_limit(self,response):
        '''
        #누적 토큰수가 임계점을 넘지 않게 한다
        #현재 토큰 사용량/최대 토큰값 을 통해 사용 비율을 알아내고
        #내가 설정한 사용가능한 토큰비율 보다 크게 사용하면  current_usage_rate-available_token_rate는 양수가 나온다
        #즉 내가 설정한 비율보다 많이 쓰면 현재 context를 줄인다.-> context가 모델의 입력이기 때문에 
        # current_usage_rate-available_token_rate가 양수라는 것은 입력+출력 토큰이 90%이상이라는 것이고 문제가 생기기전에 입력 토큰을 줄이는 것이다.
        '''
        try:
            current_usage_rate=response['usage']['total_tokens']/self.max_token_size
            exceed_token_rate=self.max_token_size-current_usage_rate
            if exceed_token_rate>0:
                #현재 context의 크기의 10%크기를 알아낸다->단순히 크기만
                remove_size=math.ceil(len(self.context)/10)
                #맨처음 system:만 남기고 ,
                # 처음부터~앞에서 10%까지의 요소는 지운다-> 이제부터 관리를 안한다 '지운'동작을 한게 아님. 
                self.context=[self.context[0]+self.context[remove_size+1:]]
        except Exception as e:
            print(f"handle_token_limit exception:{e}")
            """
        self.username=kwargs["user"]
        self.assistantname=kwargs["assistant"]
        self.memoryManager = MemoryManager()
        self.context.extend(self.memoryManager.restore_chat())

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
#스트림 출력
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
      '''
      completion출력용
      출력 토큰을 조절할수 있다
      현재 스트리밍은 출력 토큰 계산이 어려워 해당기능은 없음'''
      self.context[-1]['content']+=self.instruction
      #context문 맨 마지막에 instruction을 추가해라.
      return self._send_request_Stream()#->실제 보내는 코드는 _send_request 이다,

    def send_request(self):
        self.context[-1]['content'] += self.instruction
        return self._send_request()
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
    """
    <테스트 시나리오>대로 프로그램이 동작하도록 구성.
    1) 프로그램 구동: Chatbot 인스턴스 생성, 기본 context 포함
    2) 사용자 입력 -> context에 추가
    3) context를 API로 전송 -> 응답 수신
    4) 응답을 context에 추가, 콘솔에 출력
    5) 새 입력이 들어오면 (2)~(4) 반복
    """
    chatbot = ChatbotStream(model.advanced,system_role=system_role,instruction=instruction,user="대기",assistant="memmo")
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
            
            '''도구 실행 결과는 assistant 역할이 아닌 tool 역할로 문맥에 추가되어야 합니다.
                또한 tool_call_id를 포함해야 원본 함수 호출과 연결됩니다.
                스트리밍 요청 시 문맥이 불완전합니다.
                함수 실행 결과(tool 메시지)가 문맥에 누락되면 GPT는 도구 실행 사실을 모르고 응답을 생성합니다.
                왜 그럼 completion호출에서는 이런 문제가 안생겼나?
                실행을 할때 비록 복사된 문맥에서 함수호출을 하고 실행을 하지만 마지막 응답을 만들때 함수 실행결과를 포함해서
                context.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": func_name, 
                    "content": str(func_response)
                })#실행 결과를 문맥에 추가
                # 이런식으로 추가해줬다. 그래서 함수호출맥락을 파악한 모델은 함수호출결과를 토대로 응답을'''
            # 도구 실행 및 결과를 문맥에 추가
            temp_context=chatbot.to_openai_context()
            #temp_context=chatbot.context
            '''와 계속 안되다가 03/05/25
            이부분이 문제라는걸 발견 
            문제: 본chatbot.context에 계속 함수호출이 누적되는현상=? 함수 호출후 정상적인 결과응답을 위해서는 함수호출 문맥이 필요히나
            출력이후에는 함수 호출맥락은 필요가 없음 그래서 함수 출력후 함수호출맥락을 삭제하려함
            계획은 
            임시로 만든 temp_context에 본 문맥을 복사한뒤  임시로만든 문맥으로 출력을 생성, 그럼 정상적인 출력이 될것이고 정상적인 출력만
            뽑아내서 본 문맥에 추가할예정이었음. 
            그런데 계속 임시에 추가된내용이 본내용에도 침해됨
            원인
            원인은 파이썬의 함수 참조 였음.
            파이썬은 한번 만든 객체는 재활용하기 때문에 문제가 발생한것, 그래서 [:]로 복사를 명시했고 그결과 출력리 성공함. 
            '''
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
                    })#실행 결과를 문맥에 추가
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
            print(chatbot.context)

            

    print("===== Chatbot Finished =====")
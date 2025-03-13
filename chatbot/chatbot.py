from common import client, model,makeup_response
import sys
from characters import instruction,system_role
import math
from function_calling import FunctionCalling,tools
# 2025년 표준 API 지침 준수: 
# - POST /v1/chat/completions
# - body: { model: "gpt-...", messages: [...] }
# - 인증: "Authorization: Bearer YOUR_API_KEY"


class Chatbot:
    def __init__(self, model,system_role,instruction):
        """
        초기화:
          - context 리스트 생성 및 시스템 역할 설정
          - openai.api_key 설정
          - 사용할 모델명 저장
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
    def add_user_message_in_context(self, message: str):
        """
        사용자 메시지 추가:
          - 사용자가 입력한 message를 context에 user 역할로 추가
        """
        self.context.append({"role": "user", "content": message})
#스트림 출력
    def _send_request_Stream(self):
       
        response = client.chat.completions.create(
            model=self.model, 
            messages=self.context,
            temperature=0.5,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            stream=True
        )
        collected_text = ""
        sys.stdout.reconfigure(encoding='utf-8', write_through=True)
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
#completion출력
    def _send_request(self):
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=self.context,
                temperature=0.5,
                top_p=1,
                max_tokens=256,
                frequency_penalty=0,
                presence_penalty=0
            ).model_dump()
        except Exception as e:
            print(f"Exception 오류({type(e)}) 발생:{e}")
            if 'maximum context length' in str(e):
                self.context.pop()
                return makeup_response("메시지 조금 짧게 보내줄래?")
            else: 
                return makeup_response("[챗봇에 문제가 발생했습니다. 잠시 뒤 이용해주세요]")
            
        return response
    def send_request(self):
        self.context[-1]['content'] += self.instruction
        return self._send_request()
#대화 문맥 추가*add response 수정-> 응답객체에서 content 추출출
    def add_response(self, response):
            self.context.append({
                    "role" : response['choices'][0]['message']["role"],
                    "content" : response['choices'][0]['message']["content"],
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
if __name__ == "__main__":
    """
    <테스트 시나리오>대로 프로그램이 동작하도록 구성.
    1) 프로그램 구동: Chatbot 인스턴스 생성, 기본 context 포함
    2) 사용자 입력 -> context에 추가
    3) context를 API로 전송 -> 응답 수신
    4) 응답을 context에 추가, 콘솔에 출력
    5) 새 입력이 들어오면 (2)~(4) 반복
    """
    chatbot = Chatbot(model.basic,system_role=system_role,instruction=instruction)
    func_calling=FunctionCalling(model.basic)
    print("===== Chatbot Started =====")
    print("초기 context:", chatbot.context)
    print("사용자가 'exit'라고 입력하면 종료합니다.\n")

    while True:
        # step-2: 사용자 입력 받기
        user_input = input("User > ")
        # 'exit' 입력 시 종료
        if user_input.strip().lower() == "exit":
            print("Chatbot 종료.")
            break
        chatbot.add_user_message_in_context(user_input)
        analyzed,analyzed_dict=func_calling.analyze(user_input,tools)
        '''"message": {
        "role": "assistant",
        "content": "안녕하세요! 어떻게 도와드릴까요?",
        "tool_calls": None,
        //
        호출 안했을 때
        
      }'''

        if analyzed_dict.get("tool_calls"): 
            """함수 실행결과를 포함해 응답한 응답객체 반환"""
            response = func_calling.run( analyzed,analyzed_dict, chatbot.context[:]) 
            chatbot.get_response(response)
        
        else:    
            response = chatbot.send_request()
            #response = chatbot.send_request_Stream
            chatbot.get_response(response)
            chatbot.add_response(response)

    # 종료 시점
    print("===== Chatbot Finished =====")
from ai_app.common import client, model, makeup_response
import json
import requests
from pprint import pprint
from tavily import TavilyClient
import os
from ai_app.utils.writingRequirementsManager import WritingRequirementsManager


tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
global_lat_lon = { 
           '서울':[37.57,126.98],'강원도':[37.86,128.31],'경기도':[37.44,127.55],
           '경상남도':[35.44,128.24],'경상북도':[36.63,128.96],'광주':[35.16,126.85],
           '대구':[35.87,128.60],'대전':[36.35,127.38],'부산':[35.18,129.08],
           '세종시':[36.48,127.29],'울산':[35.54,129.31],'전라남도':[34.90,126.96],
           '전라북도':[35.69,127.24],'제주도':[33.43,126.58],'충청남도':[36.62,126.85],
           '충청북도':[36.79,127.66],'인천':[37.46,126.71],
           'Boston':[42.36, -71.05],
           '도쿄':[35.68, 139.69]
          }
global_currency_code = {'달러':'USD','엔화':'JPY','유로화':'EUR','위안화':'CNY','파운드':'GBP'}

def get_celsius_temperature(**kwargs):
    location = kwargs['location']
    lat_lon = global_lat_lon.get(location, None)
    if lat_lon is None:
        return None
    lat = lat_lon[0]
    lon = lat_lon[1]

    # API endpoint
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"

    # API를 호출하여 데이터 가져오기
    response = requests.get(url)
    # 응답을 JSON 형태로 변환
    data = response.json()
    # 현재 온도 가져오기 (섭씨)
    temperature = data['current_weather']['temperature']

    print("temperature:",temperature) 
    return temperature

def get_currency(**kwargs):    

    currency_name = kwargs['currency_name']
    currency_name = currency_name.replace("환율", "")
    currency_code = global_currency_code.get(currency_name, 'USD')
    
    if currency_code is None:
        return None

    response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{currency_code}")
    data = response.json()
    krw = data['rates']['KRW']

    print("환율:", krw) 
    return krw

def search_internet(user_input: str) -> str:
    try:
        print(f"📨 웹 검색 요청 시작: '{user_input}'")

        # ✅ 사용자 입력을 input_text 컨텍스트로 변환
        context_input = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": user_input
                    }
                ]
            }
        ]

        response = client.responses.create(
            model="gpt-4o",
            input=context_input,  # ✅ 여기!
            text={"format": {"type": "text"}},
            reasoning={},
            tools=[{
                "type": "web_search_preview",
                "user_location": {
                    "type": "approximate",
                    "country": "KR"
                },
                "search_context_size": "medium"
            }],
            tool_choice={"type": "web_search_preview"},
            temperature=1,
            max_output_tokens=2048,
            top_p=1,
            store=True
        )
        
        # ✅ 웹 검색 수행 여부 로그
        if any(getattr(item, "type", None) == "web_search_call" for item in getattr(response, "output", [])):
            print("✅ 🔍 웹 검색이 실제로 수행되었습니다.")
        else:
            print("⚠️ 웹 검색이 수행되지 않았습니다.")

        # ✅ 응답 메시지 추출
        
        # 1. message 객체 추출 (ResponseOutputMessage)
        message = next(
            (item for item in response.output if getattr(item, "type", None) == "message"),
            None
        )
        if not message:
            return "❌ GPT 응답 메시지를 찾을 수 없습니다."

        # 2. content 중 output_text 블록 추출
        content_block = next(
            (block for block in message.content if getattr(block, "type", None) == "output_text"),
            None
        )
        if not content_block:
            return "❌ GPT 응답 내 output_text 항목을 찾을 수 없습니다."

        # 3. 텍스트 추출
        output_text = getattr(content_block, "text", "").strip()

        # 4. 출처(annotation) 파싱
        annotations = getattr(content_block, "annotations", [])
        citations = []
        for a in annotations:
            if getattr(a, "type", None) == "url_citation":
                title = getattr(a, "title", "출처")
                url = getattr(a, "url", "")
                citations.append(f"[{title}]({url})")

        # 5. 텍스트 + 출처 조합
        result = output_text
        if citations:
            result += "\n\n📎 출처:\n" + "\n".join(citations)
        
        return result+"이 응답 형식 그대로 출력하세요 대답과 출처가 형식 그대로 다음대답에 담겨야합니다.엄밀하게."

    

    except Exception as e:
        return f"🚨 파싱 중 오류 발생: {str(e)}"


    except Exception as e:
        return f"🚨 오류 발생: {str(e)}"


def search_internet_for_report(**kwargs):
    #print("search_internet",kwargs)
    response =tavily.search(query=kwargs['search_query'], max_results=2, search_depth="advanced")
    contents=[{"content":result['content'],"url":result['url']}
              for result in response['results']]
    #print("contents",contents)
    return f"수집된 자료:{contents}"
report_system_role = """
다음 내용을 바탕으로 보고서를 한국어로 작성해주세요. 보고서 작성 후 마지막에 검색에 활용한 url을 각주로 반드시 표시하세요.
"""
def write_report(**kwargs):   
    print('write_report',kwargs)
    response = client.chat.completions.create(
                    timeout=90,
                    model="gpt-4-1106-preview",  
                    messages=[
                        {"role": "system", "content": report_system_role},
                        {"role": "user", "content": kwargs['materials']}
                    ],
                )
    report = response.model_dump()['choices'][0]['message']['content']
    return report
tools = [
        {
            "type": "function",
            "name": "get_celsius_temperature",
            "description": "지정된 위치의 현재 섭씨 날씨 확인",
            "strict": True,
            "parameters": {
                "type": "object",
                "required": [
                    "location"
                ],
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "광역시도, e.g. 서울, 경기"
                    }
                },
                "additionalProperties": False
            }
},
       {
           "type": "function",
            "name": "get_currency",
            "description": "지정된 통화의 원(KRW) 기준의 환율 확인.",
            "strict": True,
            "parameters": {
                "type": "object",
                "required": [
                    "currency_name"
                ],
                "properties": {
                    "currency_name": {
                        "type": "string",
                        "description": "통화명, e.g. 달러환율, 엔화환율"
                    }
                },
                "additionalProperties": False
            }
},{
"type": "function",
  "name": "search_internet",
  "description": "Searches the internet based on user input and retrieves relevant information.",
  "strict": True,
  "parameters": {
    "type": "object",
    "required": [
      "user_input"
    ],
    "properties": {
      "user_input": {
        "type": "string",
        "description": "User's search query input"
      }
    },
    "additionalProperties": False
  }
},
        {
            "type": "function",
            "name": "update_field",
            "description": """시스템이 사용자가 작성 요구사항 내의 특정 필드를 업데이트하려는 의도를 감지하면 다음 단계를 따르세요:

                        사용자가 제공한 입력에서 'field name'과 'new content'를 추출합니다.
                        추출된 'field name'을 실제 필드 식별자에 매핑합니다.
                        매핑된 필드를 'new content'로 업데이트합니다.
                        예시:

                        입력: 'The audience of the text is students.'
                        결과: audience_scope 필드를 'audience is students'로 업데이트합니다.""",
            "strict": True,
            "parameters": {
                "type": "object",
                "required": [
                    "field_name",
                    "new_content"
                ],
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "업데이트할 필드 이름 (writing_requirements 딕셔너리의 키)",
                        "enum": [
                            "purpose_background",
                            "context_topic",
                            "audience_scope",
                            "format_structure",
                            "logic_evidence",
                            "expression_method",
                            "additional_constraints",
                            "output_expectations"
                        ]
                    },
                    "new_content": {
                        "type": "string",
                        "description": "필드에 저장할 새로운 값"
                    }
                },
                "additionalProperties": False
            }
},
       {
            "type": "function",
            "name": "update_field",
            "description": """시스템이 사용자가 작성 요구 사항 내의 특정 필드를 업데이트하려고 의도하는 것을 감지하면 다음 단계를 따르세요. 
                            현재 대화 문맥에서 'field name'과 'new_content'을 추출합니다.
                            추출된 'field name'을 실제 field identifier에 매핑합니다.
                            매핑된 필드를 'new_vcontent'으로 업데이트합니다.
                            예시: 입력: '글의 대상은 학생들입니다.' 결과: audience_scope 필드를 'audience is students'로 업데이트합니다.""",
            "strict": True,
            "parameters": {
                "type": "object",
                "required": [
                    "field_name",
                    "new_content"
                ],
                "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "업데이트할 필드 이름 (writing_requirements 딕셔너리의 키)",
                        "enum": [
                            "purpose_background",
                            "context_topic",
                            "audience_scope",
                            "format_structure",
                            "logic_evidence",
                            "expression_method",
                            "additional_constraints",
                            "output_expectations"
                        ]
                    },
                    "new_content": {
                        "type": "string",
                        "description": "필드에 저장할 새로운 대화"
                    }
                },
                "additionalProperties": False  # ✅ 반드시 이 안에 위치해야 함!
            }
}
      
    ]


class FunctionCalling:
    def __init__(self, model):
        self.writingRequirementsManager=WritingRequirementsManager()
        self.available_functions = {
            "get_celsius_temperature": get_celsius_temperature,
            "get_currency": get_currency,
            "search_internet": search_internet,
            "update_field": self.writingRequirementsManager.update_field,
            "get_writing_requirement_field_content": self.writingRequirementsManager.get_field_content,
            "search_internet_for_report": search_internet_for_report,
            "write_report": write_report
        }
        self.model = model
       
    def analyze(self, user_message, tools):
    
            # 1. 모델 호출
        response = client.responses.create(
            model="gpt-4o",
            input=user_message,
            tools=tools,
            tool_choice="auto"
        )
        return response.output
    

    def run(self, analyzed,context):
 
        context.append(analyzed)
        for tool_call in analyzed:
    
            function=tool_call["function"]
            func_name=function["name"]
            #실제 함수와 연결
            func_to_call = self.available_functions[func_name]

            try:

                func_args=json.loads(function["arguments"])#딕셔너리로 변환-> 문자열이 json형태입-> 이걸 딕셔너리로 변환
                func_response=func_to_call(**func_args)
                context.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": func_name, 
                    "content": str(func_response)
                })#실행 결과를 문맥에 추가
  

            except Exception as e:
                print("Error occurred(run):",e)
                return makeup_response("[run 오류입니다]")
        return client.chat.completions.create(model=self.model,messages=context).model_dump()
    
    def run_report(self, analyzed_dict, context):
        func_name = analyzed_dict["function_call"]["name"]
        func_to_call = self.available_functions[func_name]        
        try:
            func_args = json.loads(analyzed_dict["function_call"]["arguments"])
            # 챗GPT가 알려주는 매개변수명과 값을 입력값으로하여 실제 함수를 호출한다.
            func_response = func_to_call(**func_args)
            context.append({
                "role": "function", 
                "name": func_name, 
                "content": str(func_response)
            })
            return client.chat.completions.create(model=self.model,messages=context).model_dump()            
        except Exception as e:
            print("Error occurred(run):",e)
            return makeup_response("[run 오류입니다]")

    def call_function(self, analyzed_dict):        
        func_name = analyzed_dict["function_call"]["name"]
        func_to_call = self.available_functions[func_name]                
        try:            
            func_args = json.loads(analyzed_dict["function_call"]["arguments"])
            func_response = func_to_call(**func_args)
            return str(func_response)
        except Exception as e:
            print("Error occurred(call_function):",e)
            return makeup_response("[call_function 오류입니다]")
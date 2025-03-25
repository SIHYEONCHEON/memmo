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

def search_internet(**kwargs):
    print("search_internet",kwargs)
    answer = tavily.search(query=kwargs['search_query'], include_answer=True)['answer']
    print("answer:",answer)
    return answer

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
            "type":"function",
            "function":{
            "name": "get_celsius_temperature",
            "description": "지정된 위치의 현재 섭씨 날씨 확인",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "광역시도, e.g. 서울, 경기",
                    }
                },
                "required": ["location"],
            },
        },
        },
        {
            "type":"function",
            "function":{
            "name": "get_currency",
            "description": "지정된 통화의 원(KRW) 기준의 환율 확인.",
            "parameters": {
                "type": "object",
                "properties": {
                    "currency_name": {
                        "type": "string",
                        "description": "통화명, e.g. 달러환율, 엔화환율",
                    }
                },
                "required": ["currency_name"],
            },
        },
        },
        {
            "type":"function",
            "function":{
            "name": "search_internet",
            "description": "답변 시 인터넷 검색이 필요하다고 판단되는 경우 수행",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "인터넷 검색을 위한 검색어",
                    }
                },
                "required": ["search_query"],
            }
        },
        },
        {
            "type":"function",
            "function":{
            "name": "update_field",
            "description": """
            When the system detects that a user intends to update a specific field within the writing requirements, follow these steps:
                1.  Extract the 'field name' and 'new content' from the user's provided input.
                2.  Map the extracted 'field name' to the actual field identifier.
                3.  Update the mapped field with the 'new content'.
                Example:
                * Input: 'The audience of the text is students.'
                * Result: Update the audience_scope field with 'audience is students'.""",
                "parameters": {
                "type": "object",
                "required": ["field_name","new_value"],
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
                    "new_value": {
                        "type": "string",
                        "description": "필드에 저장할 새로운 값"
                                }
            },
            }
            },
        },
        {
            "type":"function",
            "function":{
                "name": "get_writing_requirement_field_content",
                "description": """If the user wants to see the content of the writing
                  requirements fields, check the fields the user wants to see
                    (it can be one or multiple fields. If there are no fields to display,
                      determine to display all fields). Show the content of the currently written writing requirements fields.""",
                "parameters": {
                    "type": "object",
                    "required": [
                    "field_name"
                    ],
                    "properties": {
                    "field_name": {
                        "type": "string",
                        "description": "확인할 특정 필드 이름 (선택 사항). 생략하면 작성된 모든 필드 내용을 반환합니다.",
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
                    }
                    },
                
                }
                }
            }

        
    ]
func_specs_report = [#병렬 시행이 아닌 순차실행행
        {
            "name": "search_internet_for_report",
            "description": "자료를 찾기 위해 인터넷을 검색하는 함수",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "인터넷 검색을 위한 검색어",
                    }
                },
                "required": ["search_query"],
            },
        },
        {
            "name": "write_report",
            "description": "수집된 정보를 바탕으로 보고서를 작성해주는 함수",
            "parameters": {
                "type": "object",
                "properties": {
                    "materials": {
                        "type": "string",
                        "description": "사용자 메시지 중 '수집된 자료:' 리스트 안에 있는 raw data",
                    }
                },
                "required": ["materials"],
            },
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
        '''
        The response has an array of tool_calls, each with an id (used later to submit the function result) 
        and a function containing a name and JSON-encoded arguments.
        Sample response with multiple function calls
[
    {
        "id": "call_12345xyz",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": "{\"location\":\"Paris, France\"}"
        }
    },
    {
        "id": "call_67890abc",
        "type": "function",
        "function": {
            "name": "get_weather",
            "arguments": "{\"location\":\"Bogotá, Colombia\"}"
        }
    },
    {
        "id": "call_99999def",
        "type": "function",
        "function": {
            "name": "send_email",
            "arguments": "{\"to\":\"bob@email.com\",\"body\":\"Hi bob\"}"
        }
    }
]
        ('message_dict=>',
            {'audio': None,
            'content': None,
            'function_call': None,
            'refusal': None,
            'role': 'assistant',
            'tool_calls': [
                                {   'function': {
                                    'arguments': '{"location": "강원도"}',
                                    'name': 'get_celsius_temperature'},
                                'id': 'call_JMBuOBz9zydkgBLKn4p2VTkS',
                                'type': 'function'
                                    },
                                {   'function': {
                                    'arguments': '{"currency_name": "달러환율"}',
                                    'name': 'get_currency'},
                                    'id': 'call_DIv6BTRAkFDRx77vNAIiEnFO',
                                    'type': 'function'
                                        }
                                    ]
                        }
                    )'''
    def analyze(self, user_message, tools):
        try:
            response=client.chat.completions.create(
                model=model.advanced,
                messages=[{"role":"user","content":user_message}],
                tools=tools,
                tool_choice="auto",
                )
            #응답에서 메세지 추출
            analyzed = response.choices[0].message
            #메시지를 딕셔너리로 변경
            '''
        The response has an array of tool_calls, each with an id (used later to submit the function result) 
        and a function containing a name and JSON-encoded arguments.
        Sample response with multiple function calls

           'message_dict=>',
            {'audio': None,
            'content': None,
            'function_call': None,
            'refusal': None,
            'role': 'assistant',
            'tool_calls': [
                                {   'function': {
                                    'arguments': '{"location": "강원도"}',
                                    'name': 'get_celsius_temperature'},
                                '   'id': 'call_JMBuOBz9zydkgBLKn4p2VTkS',
                                    'type': 'function'
                                    },
                                {   'function': {
                                    'arguments': '{"currency_name": "달러환율"}',
                                    'name': 'get_currency'},
                                    'id': 'call_DIv6BTRAkFDRx77vNAIiEnFO',
                                    'type': 'function'
                                        }
                                    ]
                        }
                    )'''
            analyzed_dict = analyzed.model_dump()
            
            #print("analyzed_dict ***디버그\n")
            #print(message_dict)
            #print('\n**********************')
            return analyzed,analyzed_dict
            
        #메시지 딕셔너리를 반환=>
        # 이후  func_name = analyzed_dict["function_call"]["name"]
        #이런식으로 함수이름을  추출함
        #그리고 해당이름으로 함수를 가져옴
        # func_to_call = self.available_functions[func_name]
        except Exception as e:
            print("Error occurred(analyze):",e)
            return makeup_response("[analyze 오류입니다]")
    
    def analyze_function(self, user_message, func_specs):
        try:
            response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": user_message}],
                    functions=func_specs,
                    function_call="auto",
                     
                )
            message = response.choices[0].message
            message_dict = message.model_dump()
            #pprint(("message_dict=>", message_dict))
            return message_dict
        except Exception as e:
            print("Error occurred(analyze):",e)
            return makeup_response("[analyze 오류입니다]")

    def run(self, analyzed, analyzed_dict, context):
        '''"message": {
            "role": "assistant",
            "content": "안녕하세요! 어떻게 도와드릴까요?",
            "function_call": {
            * "name": "function_name",
            *"arguments": "{\"arg1\": \"value1\", \"arg2\": \"value2\"}"
            }
        }
        함수 실행에는 2개가 필요하다,실행시킬 함수와 실행시킬떄 쓰는 매개변수
        GPT가 고른 함수이름을 가져오고 
        func_name = analyzed_dict["function_call"]["name"] 
        함수를 실제로 연결한다.
        func_to_call = self.available_functions[func_name]
        '''
        context.append(analyzed)
        tool_calls = analyzed_dict['tool_calls']
        for tool_call in tool_calls:
            '''#최종적으로 tool_calls에서 {function:{}->1개,...} 를 넘김.

            #즉 for tool_call in completion.choices[0].message.tool_calls:
            #과 동일한 코드
            #name = tool_call.function.name와 동일한 코드 '''
            function=tool_call["function"]
            func_name=function["name"]
            #실제 함수와 연결
            func_to_call = self.available_functions[func_name]
            '''#
            tool_calls는
            'function': {
                              'arguments': '{"location": "강원도"}',
                              'name': 'get_celsius_temperature'},
                              'id': 'call_JMBuOBz9zydkgBLKn4p2VTkS',
                              'type': 'function'
                                    }가 원소인 리스트이다
            이것은 실행시킬 함수의 목록이다. 우리는 이목록의 처음부터 순차적으로 실행시킨다->순회
                                                
                '''
            try:
                '''처음 tool_calls 자체는 이미 딕셔너리 형태로 전달받았지만,
                function["arguments"]의 값은 여전히 문자열(string) 형태로 존재'''
                func_args=json.loads(function["arguments"])#딕셔너리로 변환-> 문자열이 json형태입-> 이걸 딕셔너리로 변환
                func_response=func_to_call(**func_args)
                '''
                도구 실행 결과는 assistant 역할이 아닌 tool 역할로 문맥에 추가되어야 합니다.
                또한 tool_call_id를 포함해야 원본 함수 호출과 연결됩니다.
                스트리밍 요청 시 문맥이 불완전합니다.
                함수 실행 결과(tool 메시지)가 문맥에 누락되면 GPT는 도구 실행 사실을 모르고 응답을 생성합니다.
                '''
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
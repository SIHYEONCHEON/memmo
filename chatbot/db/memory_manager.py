from pymongo import MongoClient
import os
from ai_app.common import today
from .db_manager import get_mongo_collection  # 새로 추가된 모듈
from .db_manager import get_pinecone_index  # Pinecone 초기화 함수 가져오기
from ai_app.common import EmbeddingModel ,client,model,today,yesterday
import json

#mongodb object create
mongo_cluster=MongoClient(os.getenv("MONGO_CLUSTER_URI"))
collection_chats = get_mongo_collection("memmo", "chats")
'''만약 환경변수 MONGO_CLUSTER_URI가 설정되어 있지 않으면, 기본값으로 mongodb://localhost:27017을 사용하게 됩니다.

오류 메시지에서 localhost:27017 연결 실패를 언급하는 것으로 보아, 환경변수가 제대로 설정되지 않았거나 Atlas URI가 아닌 로컬 MongoDB를 사용하려고 시도한 것입니다'''

#pinecone object create
pinecone_index = get_pinecone_index("memmo")

#prompt
Determine_memory_T_F="""
"If the user asks about something outside the current conversation context, respond strictly with true/false.
'''
{message}
"""
# statement1은 사용자가 떠올리려고 하는 과거 기억에 대한 질문입니다. (현재 문맥에 없을 수 있음)
# statement2는 기억 데이터베이스(DB)에서 검색되어 가져온 후보 기억 데이터입니다.
# statement2가 statement1에서 묻는 기억과 얼마나 관련 있는지(즉, 적절한 후보인지) 그 관련성 정도를 아래 json 포맷으로 답하세요.
# {"0과 1 사이의 확률": <확률값>}
MEASURING_SIMILARITY_SYSTEM_ROLE = """
statement1 is a user's question attempting to recall a specific past memory (which might be out of the current context).
statement2 is a candidate memory data retrieved from a memory database (DB).
Evaluate the degree of relevance between statement2 and the specific memory the user is asking about in statement1 (i.e., how appropriate statement2 is as a candidate answer). Answer in the following JSON format.
"과거" 라는 말이있다면 이것을 반드시 실행하세요요
{"probability": <between 0 and 1>}
"""

''' 사용 예시 (가상)
statement1 = "우리가 작년에 갔던 바닷가 이름 뭐였지?" # 현재 대화 문맥에는 없음
statement2 = "작년 여름에 민지랑 고비랑 같이 갔던 해변은 대천해수욕장이었어." # 특정 기억 내용

# AI 모델이 위 프롬프트 지침에 따라 statement1과 statement2를 평가하여 아래와 같은 JSON 출력
# {"probability": 0.95}'''
class MemoryManager:

    def save_chat(self,context):
        messages=[]
        for message in context:
            if message.get("saved",True):
                continue
            #문맥속 저장되지 않은 값만 골라낸다.
            messages.append({"date":today(), "role": message["role"], "content": message["content"]})

        #messages에 한개라도 값이 있다면 콜랙션에 값을 넣어라=>몽고디비안에 넣어라라
        if len(messages)>0:
            collection_chats.insert_many(messages)
            '''insert_many()는 MongoDB 컬렉션에 여러 개의 데이터를 한 번에 저장할 때 사용하는 함수
            MongoDB에서는 데이터를 문서(document) 단위로 저장합니다.
            **insert_one()**은 하나의 문서(하나의 데이터)를 저장할 때 사용합니다.
            **insert_many()**는 한 번에 여러 개의 문서를 저장할 때 사용합니다.
            지금 코드에서는 저장할 '문서'가 message임.
            '''
   
    def restore_chat(self,date=None):
        '''특정 날짜에 저장한 값(들들)을 context자료구조 형태로 받아옴'''
        search_date= date if date is not None else today()#특정 날짜를 준다면 그날짜로 아니면 현재 날짜로
        search_results=collection_chats.find({"date": search_date})
        restored_chat=[{"role": v["role"], "content": v["content"], "saved": True} for v in search_results]
        return restored_chat
    
    def needs_memory(self, message):
        #기억 검색 여부 판단
        context = [{"role": "user", "content": Determine_memory_T_F.format(message=message)}] 
        try:
            response = client.chat.completions.create(
                        model=model.advanced, #gpt-4-1106-preview
                        messages=context,
                        temperature=0,
                    ).model_dump()
            print("needs_memory response:", response)
            print("needs_memory", response['choices'][0]['message']['content'])
            print("\n")
            #대답을 대문자로 변환
            return True if response['choices'][0]['message']['content'].upper() == "TRUE" else False          
        except Exception:
            print("Except!")
            return False
    def search_vector_db(self, message):
        '''
        사용자 입력 벡터DB로 검색
        원리:
        사용자의 입력 메시지를 OpenAI 임베딩으로 벡터화한 후,
        이 벡터와 가장 유사한(의미적으로 가까운) 데이터를 Pinecone에서 찾아 그 결과를 반환
            '''
        #객체(response)의 data 속성(리스트)의 첫 번째 요소에 접근하고, 다시 그 요소의 embedding 속성에 접근
        query_vector = client.embeddings.create(input=message, model=EmbeddingModel.ada).data[0].embedding
        results= pinecone_index.query(
            top_k=1,
            vector=query_vector,
            include_metadata=True,
        )
        id = results['matches'][0]['id']
        score = results['matches'][0]['score']
        #검색결과 확인인
        print("id",id, "score",score)
        #유사도가 낮은 값은 검색 내용과 먼 결과라고 판단.
        return id if score > 0.7 else None 
   
   #이후 검색 아이디로 몽고 디비에 원본 검색
    def search_mongo_db(self, _id):
        '''벡터 검색으로 얻은 id로 몽고db에서 원본 검색 '''
        search_result = collection_chats.find_one({"_id": int(_id)})
        #id로 검색된 원본 가져오기
        print("search_result", search_result)
        return search_result["summary"]#요약에 해당되는 부분 가져오기
    #검색 메소드 종합
    def retrieve_memory(self, message):
        vector_id = self.search_vector_db(message)
        if not vector_id:
            return None
        #뭐라도 벡터db가 나왔다면(유사도 높은 id일 것이다) 본데이터의 실용성 검사
        memory = self.search_mongo_db(vector_id)        
        if self.filter(message, memory):
            return memory
        else:
            return None

    def filter(self, message, memory, threshhold=0.6):
        '''검색된 내용이 사용자가 기억하려는 내용이 맞는지 유사도 검사'''
        context = [
            {"role": "system", "content": MEASURING_SIMILARITY_SYSTEM_ROLE},
            {"role": "user", "content": f'{{"statement1": "민지:{message}, "statement2": {memory}}}'}
        ] 
        try:
            response = client.chat.completions.create(
                model=model.advanced, #gpt-4-1106-preview
                messages=context,
                temperature=0,
                response_format={"type":"json_object"}
            ).model_dump()
            prob = json.loads(response['choices'][0]['message']['content'])['probability']
            print("유사도:", prob)
        except Exception as e:
            print("filter error", e)
            prob = 0
        return prob >= threshhold #유사도가 0.6 이상이면 통과






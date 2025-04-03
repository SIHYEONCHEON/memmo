from pymongo import MongoClient
import os
from pinecone import Pinecone

def get_mongo_collection(db_name: str, collection_name: str):
    """
    Returns a MongoDB collection object.
    """
    mongo_cluster = MongoClient(os.getenv("MONGO_CLUSTER_URI"))
    db = mongo_cluster[db_name]
    return db[collection_name]

def get_pinecone_index(index_name: str):
    """
    Pinecone 인덱스를 초기화하고 반환합니다.
    :param index_name: 사용할 Pinecone 인덱스 이름
    :return: Pinecone Index 객체
    """
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY 환경 변수가 설정되지 않았습니다.")
    
    pc = Pinecone(pinecone_api_key)
    return pc.Index(index_name)

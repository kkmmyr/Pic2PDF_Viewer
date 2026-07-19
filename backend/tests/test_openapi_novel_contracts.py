"""novel_db のOpenAPIレスポンスが具体型を公開することを検証する。"""


def test_novel_response_models_are_concrete(client):
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]

    qa_items = components["QaHistoryResponse"]["properties"]["items"]["items"]
    search_hits = components["SearchResponse"]["properties"]["hits"]["items"]
    assert qa_items["$ref"].endswith("/QaHistoryItemOut")
    assert search_hits["$ref"].endswith("/SearchHitOut")

    paths = schema["paths"]
    qa_detail = paths["/api/novel_db/qa/history/{history_id}"]["get"]["responses"]["200"]["content"]
    chat_detail = paths["/api/novel_db/sessions/{session_id}"]["get"]["responses"]["200"]["content"]
    assert qa_detail["application/json"]["schema"]["$ref"].endswith("/QaHistoryDetailResponse")
    assert chat_detail["application/json"]["schema"]["$ref"].endswith("/ChatSessionDetailPayload")

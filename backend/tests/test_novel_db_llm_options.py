from services.novel_db.llm_options import make_llm_options


def test_make_llm_options_omits_optional_repeat_penalty():
    assert make_llm_options(temperature=0.1, num_predict=256, num_ctx=4096) == {
        "temperature": 0.1,
        "num_predict": 256,
        "num_ctx": 4096,
    }


def test_make_llm_options_includes_repeat_penalty():
    assert (
        make_llm_options(temperature=0.2, repeat_penalty=1.15, num_predict=1024, num_ctx=8192)["repeat_penalty"] == 1.15
    )

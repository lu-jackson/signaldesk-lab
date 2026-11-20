"""A3：草稿只附相關事實；免費書與付費書不混淆；禁語不出現在任何預設事實裡。"""
from app.providers.ai_demo import draft_text, pick_facts
from app.seed import BRANDS

NAME, DATA = BRANDS["brand_notes"]
BRAND = {"name": NAME, "data": DATA}


def draft(text: str) -> str:
    return draft_text({"text": text, "author_handle": "demo_u1"}, BRAND, {})


def test_calculus_post_gets_calculus_fact_and_no_unrelated_book():
    body = draft("微積分期末快到了，積分技巧看不懂，求推薦整理好的微積分筆記。")
    assert "微積分筆記共 338 頁" in body
    assert "線性代數筆記" not in body and "高中公民筆記共" not in body


def test_civics_post_gets_free_book_not_paid_price():
    body = draft("高中公民要考學測了，有沒有免費的高中公民重點整理？")
    assert "高中公民筆記共 89 頁" in body and "完全免費" in body
    assert "NT$800" not in body.split("高中公民筆記共 89 頁")[0]


def test_paid_book_never_called_free_download():
    body = draft("統計學假設檢定看不懂，求推薦整理好的筆記")
    assert "統計學筆記共 143 頁" in body and "買斷 NT$800" in body
    assert "完全免費" not in body.split("統計學筆記共 143 頁")[1].split("\n")[0]


def test_no_relevant_fact_means_no_fact_attached():
    assert pick_facts(DATA["facts"], "今天天氣真好，適合去騎車。") == []


def test_at_most_two_facts_and_second_only_when_relevant():
    one = pick_facts(DATA["facts"], "想找微積分筆記")
    assert 1 <= len(one) <= 2
    assert not any("線性代數" in f for f in one)


def test_default_facts_do_not_contain_forbidden_phrases():
    blob = "\n".join(DATA["facts"] + [f["a"] for f in DATA["faq"]] + [DATA["cta"]])
    assert [b for b in DATA["forbidden"] if b in blob] == []


def test_macro_post_gets_macro_fact_only():
    body = draft("想找總體經濟的複習筆記，期末快到了，有人推薦嗎？")
    assert "總體經濟筆記共 168 頁" in body
    assert "線性代數筆記" not in body and "個體經濟筆記共" not in body


def test_civics_post_does_not_attach_unrelated_paid_book():
    body = draft("高中公民要考學測了，有沒有免費的高中公民重點整理？")
    assert "高中公民筆記共 89 頁" in body
    assert "總體經濟筆記共" not in body and "高中英文筆記共" not in body


def test_sharing_question_gets_license_answer_without_forbidden_phrase():
    body = draft("可以把筆記分享給同學嗎？")
    assert "浮水印" in body and "不能轉傳" in body
    assert all(bad not in body for bad in DATA["forbidden"])

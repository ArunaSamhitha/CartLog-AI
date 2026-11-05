from cartlog.understanding import parse_text_rules


def test_budget_and_condition():
    q = parse_text_rules("find me used sony headphones under $150")
    assert q.max_price == 150
    assert q.condition == "used"
    assert "sony headphones" in q.product


def test_k_suffix_budget():
    assert parse_text_rules("gaming laptop under 1.5k").max_price == 1500


def test_plain_dollar_amount_and_no_condition():
    q = parse_text_rules("standing desk $300")
    assert q.max_price == 300
    assert q.condition == "any"


def test_no_budget():
    q = parse_text_rules("a new kindle paperwhite")
    assert q.max_price is None
    assert q.condition == "new"
    assert q.product == "kindle paperwhite"

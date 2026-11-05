from cartlog.ranking import rank
from cartlog.schemas import ProductQuery, Research


def _item(market, title, price, **kw):
    return {"marketplace": market, "title": title, "price": price, "url": "https://example.com", **kw}


def test_relevant_cheaper_listing_ranks_first():
    q = ProductQuery(product="headphones", brand="Sony")
    results = {
        "ebay": {"listings": [_item("ebay", "Phone case", 10), _item("ebay", "Sony headphones", 120)]},
        "amazon": {"listings": [_item("amazon", "Sony headphones", 300)]},
    }
    ranked = rank(results, q, Research(summary="", typical_price_range=(150, 250)))
    assert ranked[0].title == "Sony headphones" and ranked[0].price == 120
    assert ranked[-1].title == "Phone case"


def test_duplicates_removed_and_missing_agent_tolerated():
    q = ProductQuery(product="mouse")
    results = {"ebay": {"listings": [_item("ebay", "Mouse", 20), _item("ebay", "mouse", 20)]}}
    assert len(rank(results, q, None)) == 1

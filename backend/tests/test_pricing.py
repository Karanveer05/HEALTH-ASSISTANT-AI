"""Price comparison logic, tested on recorded product shapes from each site (no network)."""
from app import pricing

SRC = {"name": "Site", "search": "https://site.test/search?q={q}", "product_prefix": "https://site.test/p/"}


def test_pack_units():
    assert pricing.pack_units("15 Tablet(s) in Strip", "Dolo 650Mg Strip Of 15 Tablets") == (15, "tablet")
    assert pricing.pack_units("", "Dolo-650 Tablet 15's") == (15, "tablet")      # "650" must not be read as the count
    assert pricing.pack_units("15 tablets", "Dolo 650 Tablet") == (15, "tablet")
    assert pricing.pack_units("60ml Syrup in Bottle", "Citephi 5Mg Bottle Of 60Ml Syrup") == (60, "ml")
    assert pricing.pack_units("", "Electral Sachet 4.4 gm") == (1, "sachet")
    assert pricing.pack_units("", "ELECTRAL POWDER 4.40gm Sachet 1's") == (1, "sachet")
    assert pricing.pack_units("", "Some Cream 20gm") == (None, None)


def test_whole_word_matching():
    assert pricing._has_word("dolo 650mg strip", "650")
    assert pricing._has_word("dolo-650 tablet", "dolo")
    assert not pricing._has_word("dolofirst 650 mg", "dolo")
    assert not pricing._has_word("pancooly 40mg", "pan")


def test_price_shapes_from_each_site():
    raw = [
        {"name": "Dolo 650Mg Strip Of 15 Tablets", "salePriceDecimal": "23.89", "mrpDecimal": "32.28",
         "measurementUnit": "15 Tablet(s) in Strip", "slug": "dolo-650"},                                   # PharmEasy
        {"name": "Dolo 650 Tablet 15's", "slug": "dolo-650-nm", "price": {"effective": {"min": 25.18}, "marked": {"min": 32.28}}},  # Netmeds
        {"name": "<b>Dolo 650 Tablet</b>", "url": "/drugs/dolo-650-tablet-74467", "label": "15 tablets",
         "prices": {"mrp": "₹32.28", "discounted_price": None}},                                             # 1mg, no discount
        {"name": "Dolo-650 Tablet 15's", "price": 32.0, "specialPrice": 30.0, "urlKey": "dolo-650mg"},      # Apollo
    ]
    offers = pricing._to_offers(SRC, raw, "dolo 650")
    by_name = {o["name"]: o for o in offers}
    assert by_name["Dolo 650Mg Strip Of 15 Tablets"]["price"] == 23.89 and by_name["Dolo 650Mg Strip Of 15 Tablets"]["mrp"] == 32.28
    assert by_name["Dolo 650 Tablet 15's"]["price"] == 25.18 and by_name["Dolo 650 Tablet 15's"]["mrp"] == 32.28
    one_mg = by_name["Dolo 650 Tablet"]  # html tags stripped, MRP used when there is no discount
    assert one_mg["price"] == 32.28 and one_mg["url"] == "https://site.test/drugs/dolo-650-tablet-74467" and one_mg["units"] == 15
    apollo = by_name["Dolo-650 Tablet 15's"]
    assert apollo["price"] == 30.0 and apollo["mrp"] == 32.0 and apollo["discount_pct"] == 6


def test_best_match_skips_lookalikes_and_combos():
    raw = [
        {"name": "Dolofirst 650mg Tablet", "price": 21.4, "label": "15 tablets"},
        {"name": "Combo Pack of Saridon + Dolo 650 Tablet", "price": 50.0},
        {"name": "Dolo 650 Tablet", "price": 31.0, "label": "15 tablets"},
    ]
    best = pricing._best_match(pricing._to_offers(SRC, raw, "dolo 650"))
    assert best["name"] == "Dolo 650 Tablet"


def test_cheapest_compares_per_tablet_and_like_with_like():
    a = {"source": "A", "price": 30.0, "units": 15, "unit": "tablet", "per_unit": 2.0}
    b = {"source": "B", "price": 25.0, "units": 10, "unit": "tablet", "per_unit": 2.5}  # cheaper pack, dearer per tablet
    c = {"source": "C", "price": 10.0, "units": 60, "unit": "ml", "per_unit": 0.17}     # syrup: not comparable
    cheapest, basis = pricing._cheapest([a, b, c])
    assert cheapest["source"] == "A" and basis == "per_unit"
    assert c["comparable"] is False and a["comparable"] and b["comparable"]

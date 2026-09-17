import pytest

from vessel_chat.normalize import norm_company, norm_name, ship_type_group


def test_norm_name_ignores_case_spacing_and_punctuation():
    assert norm_name("  Kota-Gaya ") == norm_name("KOTA GAYA") == "KOTA GAYA"
    assert norm_name("M.V.  sea   star") == "MV SEA STAR"
    assert norm_name(None) == ""


@pytest.mark.parametrize(
    "a,b",
    [
        ("EVERGREEN MARINE CORP.", "Evergreen Marine Corporation"),
        ("BW LPG HOLDING PTE LTD", "BW LPG HOLDING LTD"),
        ("NANJING SHENGHANG SHIPPING CO LTD", "Nanjing Shenghang Shipping Co."),
        ("FIRST STEAMSHIP CO LTD", "FIRST STEAMSHIP SA"),
    ],
)
def test_norm_company_merges_legal_suffix_variants(a, b):
    assert norm_company(a) == norm_company(b)


def test_norm_company_keeps_distinct_entities_apart():
    assert norm_company("EVERGREEN MARINE CORP") == "EVERGREEN MARINE"
    assert norm_company("EVERGREEN MARINE ASIA PTE LTD") == "EVERGREEN MARINE ASIA"
    assert norm_company("EVERGREEN MARINE HONG KONG") != norm_company("EVERGREEN MARINE CORP")


def test_norm_company_does_not_strip_suffix_words_inside_name():
    # "CO" chỉ bị bỏ khi là hậu tố pháp lý ở cuối, không bỏ ở đầu/giữa tên
    assert norm_company("CO OPERATIVE SHIPPING LTD") == "CO OPERATIVE SHIPPING"


@pytest.mark.parametrize(
    "label,group",
    [
        ("Tanker(s), all ships of this type", "tanker"),
        ("Tanker(s), carrying DG and/or MHB, HS, or MP, IMO hazard or pollutant category Y", "tanker"),
        ("Cargo ships, no additional information", "cargo"),
        ("Cargo ship, landing craft", "cargo"),
        ("Fishing vessel", "fishing"),
        ("Tugs", "tug"),
        ("Towing and length of the tow exceeds 200 m or breadth exceeds 25 m", "tug"),
        ("Passenger (cruise) ship", "passenger"),
        ("HSC, all ships of this type", "high_speed"),
        ("Pleasure motor craft", "pleasure"),
        ("Sailing vessel", "pleasure"),
        ("Dredger", "special"),
        ("Law enforcement vessels", "special"),
        ("Other types of ship", "other"),
        ("Not available", "unknown"),
        ("Reserved for future use", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_ship_type_group(label, group):
    assert ship_type_group(label) == group

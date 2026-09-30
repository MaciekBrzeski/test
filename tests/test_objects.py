import pytest

from pixelpdf.pdf.objects import Name, Ref, Stream, serialize


@pytest.mark.parametrize("value, expected", [
    (None, b"null"),
    (True, b"true"),
    (False, b"false"),
    (42, b"42"),
    (-7, b"-7"),
    (0.5, b"0.5"),
    (595.25, b"595.25"),
    (1.0, b"1"),
    (-0.0, b"0"),
    (1e-9, b"0"),
    (Name("Type"), b"/Type"),
    (Name("A B#"), b"/A#20B#23"),
    (Ref(3), b"3 0 R"),
    ("a(b)c\\", b"(a\\(b\\)c\\\\)"),
    ("line\nbreak", b"(line\\nbreak)"),
    (b"\x00\xff", b"<00FF>"),
    ([1, Name("X"), [2.5]], b"[1 /X [2.5]]"),
    ({"Type": Name("Page"), "Count": 2}, b"<</Type /Page /Count 2>>"),
])
def test_serialize(value, expected):
    assert serialize(value) == expected


def test_non_latin1_string_uses_utf16():
    assert serialize("Ł") == b"(\xfe\xff\x01A)"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), object()])
def test_serialize_rejects_invalid(bad):
    with pytest.raises((TypeError, ValueError)):
        serialize(bad)


def test_stream_must_be_indirect():
    with pytest.raises(TypeError):
        serialize([Stream({}, b"x")])

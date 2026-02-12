import os
import tempfile

from airsoft_suitcase.game_utils import (
    EXIT_CODE,
    KEYPAD_CHARACTERS,
    generate_code,
    is_truthy,
    read_audio_setting,
)


class TestIsTruthy:
    def test_none_returns_false(self) -> None:
        assert is_truthy(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert is_truthy("") is False

    def test_truthy_values(self) -> None:
        for value in ("1", "true", "True", "TRUE", "yes", "Yes", "on", "ON"):
            assert is_truthy(value) is True, f"Expected {value!r} to be truthy"

    def test_falsy_values(self) -> None:
        for value in ("0", "false", "no", "off", "random", "maybe"):
            assert is_truthy(value) is False, f"Expected {value!r} to be falsy"

    def test_whitespace_stripped(self) -> None:
        assert is_truthy("  true  ") is True
        assert is_truthy("  false  ") is False


class TestGenerateCode:
    def test_correct_length(self) -> None:
        for length in (1, 4, 8, 16):
            code = generate_code(length)
            assert len(code) == length

    def test_zero_length_returns_empty(self) -> None:
        assert generate_code(0) == ""

    def test_negative_length_returns_empty(self) -> None:
        assert generate_code(-5) == ""

    def test_only_valid_characters(self) -> None:
        code = generate_code(100)
        for char in code:
            assert char in KEYPAD_CHARACTERS, f"Unexpected character: {char!r}"

    def test_custom_charset(self) -> None:
        code = generate_code(10, charset="AB")
        assert all(c in "AB" for c in code)

    def test_empty_charset_raises(self) -> None:
        try:
            generate_code(5, charset="")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass


class TestReadAudioSetting:
    def test_missing_file_returns_default(self) -> None:
        assert read_audio_setting("/nonexistent/path.csv", default=True) is True
        assert read_audio_setting("/nonexistent/path.csv", default=False) is False

    def test_audio_true(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("Audio:True\n")
            f.flush()
            try:
                assert read_audio_setting(f.name) is True
            finally:
                os.unlink(f.name)

    def test_audio_false(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("Audio:false\n")
            f.flush()
            try:
                assert read_audio_setting(f.name) is False
            finally:
                os.unlink(f.name)

    def test_no_audio_key_returns_default(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("Volume:50\n")
            f.flush()
            try:
                assert read_audio_setting(f.name, default=True) is True
            finally:
                os.unlink(f.name)


class TestConstants:
    def test_exit_code_is_string(self) -> None:
        assert isinstance(EXIT_CODE, str)
        assert len(EXIT_CODE) == 4

    def test_keypad_characters(self) -> None:
        assert len(KEYPAD_CHARACTERS) == 14
        assert "0" in KEYPAD_CHARACTERS
        assert "9" in KEYPAD_CHARACTERS
        assert "A" in KEYPAD_CHARACTERS
        assert "D" in KEYPAD_CHARACTERS

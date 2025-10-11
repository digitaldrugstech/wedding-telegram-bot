"""Tests for app/utils/formatters.py"""

from app.utils.formatters import format_diamonds


class TestFormatDiamonds:
    """Test diamond formatting with Russian word endings."""

    def test_single_diamond(self):
        """Test singular form (1 алмаз)."""
        assert format_diamonds(1) == "1 алмаз"
        assert format_diamonds(21) == "21 алмаз"
        assert format_diamonds(101) == "101 алмаз"

    def test_few_diamonds(self):
        """Test genitive singular form (2-4 алмаза)."""
        assert format_diamonds(2) == "2 алмаза"
        assert format_diamonds(3) == "3 алмаза"
        assert format_diamonds(4) == "4 алмаза"
        assert format_diamonds(22) == "22 алмаза"
        assert format_diamonds(104) == "104 алмаза"

    def test_many_diamonds(self):
        """Test genitive plural form (5+ алмазов)."""
        assert format_diamonds(0) == "0 алмазов"
        assert format_diamonds(5) == "5 алмазов"
        assert format_diamonds(10) == "10 алмазов"
        assert format_diamonds(11) == "11 алмазов"
        assert format_diamonds(100) == "100 алмазов"
        assert format_diamonds(1000) == "1000 алмазов"

    def test_teens_exception(self):
        """Test exception for 11-14 (always алмазов)."""
        assert format_diamonds(11) == "11 алмазов"
        assert format_diamonds(12) == "12 алмазов"
        assert format_diamonds(13) == "13 алмазов"
        assert format_diamonds(14) == "14 алмазов"
        assert format_diamonds(111) == "111 алмазов"
        assert format_diamonds(112) == "112 алмазов"

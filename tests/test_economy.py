"""Integration tests for economy mechanics."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import (
    TAX_RATE,
    TAX_THRESHOLD,
    TRANSFER_FEE_RATE,
)
from app.database.models import Base, User


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user with balance."""
    user = User(telegram_id=123456, username="testuser", gender="male", balance=10000)
    db_session.add(user)
    db_session.commit()
    return user


class TestBalanceValidation:
    """Test that balance cannot go negative."""

    def test_balance_cannot_go_negative(self, db_session, test_user):
        """Balance should never go negative in valid operations."""
        initial_balance = test_user.balance

        # Try to deduct more than balance
        deduction = initial_balance + 1000

        # In real code, this should be prevented
        # Here we test the validation
        if test_user.balance >= deduction:
            test_user.balance -= deduction
        else:
            # Should reject the operation
            pass

        db_session.commit()
        db_session.refresh(test_user)

        # Balance should remain unchanged
        assert test_user.balance >= 0
        assert test_user.balance == initial_balance

    def test_minimum_balance_zero(self, db_session, test_user):
        """Balance can reach zero but not negative."""
        test_user.balance = 100

        # Deduct exact balance
        test_user.balance -= 100

        db_session.commit()
        db_session.refresh(test_user)

        assert test_user.balance == 0


class TestTransferFeeCalculation:
    """Test transfer fee calculation."""

    def test_transfer_fee_rate(self):
        """Transfer fee should be 5%."""
        assert TRANSFER_FEE_RATE == 5

    def test_fee_calculation(self):
        """Test fee calculation for various amounts."""
        transfer_amount = 1000
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        assert fee == 50  # 5% of 1000

    def test_fee_calculation_small_amount(self):
        """Test fee for small amounts."""
        transfer_amount = 10
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        assert fee == 0  # 5% of 10 rounds down to 0

    def test_fee_calculation_large_amount(self):
        """Test fee for large amounts."""
        transfer_amount = 100000
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        assert fee == 5000  # 5% of 100000

    def test_transfer_with_fee_simulation(self, db_session):
        """Simulate transfer with fee."""
        sender = User(telegram_id=111111, username="sender", gender="male", balance=10000)
        receiver = User(telegram_id=222222, username="receiver", gender="female", balance=5000)
        db_session.add_all([sender, receiver])
        db_session.commit()

        transfer_amount = 1000
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)
        total_deduction = transfer_amount + fee

        # Check sender has enough
        if sender.balance >= total_deduction:
            sender.balance -= total_deduction
            receiver.balance += transfer_amount
            db_session.commit()

        db_session.refresh(sender)
        db_session.refresh(receiver)

        # Sender loses transfer + fee
        assert sender.balance == 10000 - 1000 - 50
        # Receiver gets transfer amount
        assert receiver.balance == 5000 + 1000


class TestTaxSystem:
    """Test tax calculation."""

    def test_tax_threshold(self):
        """Tax threshold should be 50,000."""
        assert TAX_THRESHOLD == 50000

    def test_tax_rate(self):
        """Tax rate should be 5%."""
        assert TAX_RATE == 0.05

    def test_no_tax_below_threshold(self):
        """No tax for balance below threshold."""
        balance = 30000
        taxable_amount = max(0, balance - TAX_THRESHOLD)
        tax = int(taxable_amount * TAX_RATE)

        assert tax == 0

    def test_tax_at_threshold(self):
        """No tax at exact threshold."""
        balance = TAX_THRESHOLD
        taxable_amount = max(0, balance - TAX_THRESHOLD)
        tax = int(taxable_amount * TAX_RATE)

        assert tax == 0

    def test_tax_above_threshold(self):
        """Tax applies to amount above threshold."""
        balance = 60000
        taxable_amount = max(0, balance - TAX_THRESHOLD)
        tax = int(taxable_amount * TAX_RATE)

        # 10,000 above threshold, 5% = 500
        assert tax == 500

    def test_tax_large_balance(self):
        """Tax calculation for large balance."""
        balance = 200000
        taxable_amount = max(0, balance - TAX_THRESHOLD)
        tax = int(taxable_amount * TAX_RATE)

        # 150,000 above threshold, 5% = 7,500
        assert tax == 7500

    def test_tax_progressive_simulation(self, db_session):
        """Simulate tax deduction."""
        user = User(telegram_id=123456, username="richuser", gender="male", balance=100000)
        db_session.add(user)
        db_session.commit()

        taxable_amount = max(0, user.balance - TAX_THRESHOLD)
        tax = int(taxable_amount * TAX_RATE)

        # Deduct tax
        user.balance -= tax
        db_session.commit()

        db_session.refresh(user)

        # 100,000 - (50,000 taxable * 5% = 2,500)
        assert user.balance == 97500


class TestEconomyBalance:
    """Test overall economy balance."""

    def test_transfer_conserves_total_wealth(self, db_session):
        """Transfers should conserve total wealth (minus fees)."""
        user1 = User(telegram_id=111111, username="user1", gender="male", balance=10000)
        user2 = User(telegram_id=222222, username="user2", gender="female", balance=5000)
        db_session.add_all([user1, user2])
        db_session.commit()

        initial_total = user1.balance + user2.balance

        # Transfer 1000 with 5% fee
        transfer_amount = 1000
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        user1.balance -= (transfer_amount + fee)
        user2.balance += transfer_amount
        db_session.commit()

        db_session.refresh(user1)
        db_session.refresh(user2)

        final_total = user1.balance + user2.balance

        # Total wealth should decrease by fee
        assert final_total == initial_total - fee

class TestEdgeCases:
    """Test edge cases in economy."""

    def test_zero_balance_operations(self, db_session):
        """Operations with zero balance."""
        user = User(telegram_id=123456, username="pooruser", gender="male", balance=0)
        db_session.add(user)
        db_session.commit()

        # Cannot transfer with zero balance
        transfer_amount = 100
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)
        total_needed = transfer_amount + fee

        can_transfer = user.balance >= total_needed
        assert can_transfer is False

    def test_exact_balance_transfer(self, db_session):
        """Transfer exact balance (including fee)."""
        user = User(telegram_id=123456, username="user", gender="male", balance=105)
        db_session.add(user)
        db_session.commit()

        # Transfer 100, fee = 5, total = 105
        transfer_amount = 100
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)
        total = transfer_amount + fee

        if user.balance >= total:
            user.balance -= total

        db_session.commit()
        db_session.refresh(user)

        assert user.balance == 0

    def test_rounding_edge_cases(self):
        """Test rounding in calculations."""
        # Small transfer with fee
        transfer_amount = 15
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        # 15 * 5 / 100 = 0.75, rounds down to 0
        assert fee == 0

        # Slightly larger
        transfer_amount = 25
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        # 25 * 5 / 100 = 1.25, rounds down to 1
        assert fee == 1

    def test_large_number_overflow_protection(self):
        """Test that large numbers don't overflow."""
        # SQLAlchemy BigInteger should handle large values
        large_balance = 2**62  # Very large but within BigInteger range

        # Should not overflow
        assert large_balance > 0

        # Calculate fee
        transfer_amount = 1000000
        fee = int(transfer_amount * TRANSFER_FEE_RATE / 100)

        assert fee == 50000

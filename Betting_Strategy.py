"""$10 -> $15 -> $20 betting progression, based on each round's net profit.

Use next_bet before dealing and record_result after settling the entire round,
including all split hands, doubles, and blackjack payouts. Positive profit
advances the progression, negative profit resets it, and zero holds the bet.
After a settled $20 round, reset unless the round is a push.

Amounts are in dollars. This module sizes the opening bet only; the engine
handles bankroll accounting and funds needed for doubles and splits.
"""

from decimal import Decimal, InvalidOperation


class BettingStrategy:
    """Keep an independent progression for one player or simulation."""

    progression = (10, 15, 20)

    def __init__(self):
        self._step = 0

    @property
    def next_bet(self):
        """Opening wager for the next round, in dollars."""
        return self.progression[self._step]

    def record_result(self, net_profit):
        """Record signed round profit and return the next opening wager.

        Pass profit, not total chips returned: a normal $10 win is +10,
        a $10 loss is -10, and a push is 0. For split hands, pass their
        combined net profit once after all hands have settled.
        """
        try:
            profit = Decimal(str(net_profit))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("net_profit must be a finite dollar amount") from exc
        if not profit.is_finite():
            raise ValueError("net_profit must be a finite dollar amount")

        if profit < 0:
            self.reset()
        elif profit > 0:
            self._step = (self._step + 1) % len(self.progression)
        return self.next_bet

    def reset(self):
        """Start a new session at $10."""
        self._step = 0


class FlatTen(BettingStrategy):
    """Bet $10 every round, regardless of the previous result."""

    progression = (10,)


class ShortPress(BettingStrategy):
    """$10 -> $15; reset after a loss or a $15 win; hold on pushes."""

    progression = (10, 15)


class ThreeStepDoubling(BettingStrategy):
    """$10 -> $20 -> $40; reset after a loss or a final-step win."""

    progression = (10, 20, 40)


class WinBankThenPress(BettingStrategy):
    """$10 -> $10 -> $20 -> $40; bank the first ordinary $10 win.

    A push holds the step; any loss or a final-step win resets to step one.
    Banked money remains part of the bankroll, as with the other strategies.
    """

    progression = (10, 10, 20, 40)


class AlternatingThreeStep(ThreeStepDoubling):
    """$10 -> $20 -> ($40 or $80), alternating resolved third-step bets.

    Start each session with use_80 = 0. A $40 third-step win or loss sets
    it to 1; an $80 third-step win or loss sets it to 0. Earlier losses
    reset the step without changing the flag. Pushes hold both the bet
    and flag. Doubles/splits count as one round, using combined net profit.
    """

    def __init__(self):
        super().__init__()
        self.use_80 = 0

    @property
    def next_bet(self):
        if self._step == 2 and self.use_80 == 1:
            return 80
        return super().next_bet

    def record_result(self, net_profit):
        was_third_step = self._step == 2
        super().record_result(net_profit)
        # The base class validates input and leaves step 2 intact on pushes.
        if was_third_step and self._step == 0:
            self.use_80 = 1 - self.use_80
        return self.next_bet


STRATEGIES = {
    'flat_10': FlatTen,
    'short_press': ShortPress,
    'current': BettingStrategy,
    'three_step_doubling': ThreeStepDoubling,
    'win_bank_then_press': WinBankThenPress,
    'alternating_three_step': AlternatingThreeStep,
}

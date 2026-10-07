"""Run the blackjack backtest using Perfect_Play and Betting_Strategy.

Usage:
    python Main.py
    python Main.py --sessions 100000 --seed 42

Runs 100,000 sessions each for flat $10, short press ($10/$15),
and three-step doubling ($10/$20/$40) in parallel.
All use a $500 bankroll, $550 profit threshold, $250 loss threshold,
and no round limit. Pushes hold the step; losses reset the progression.
Results are saved in results/flat_short_three_step_comparison beside this file.
"""

from Backtest import main


if __name__ == '__main__':
    main()

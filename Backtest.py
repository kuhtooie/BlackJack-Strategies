"""Compare flat $10, short press, and three-step bets at 10% take profit.

Run: python Backtest.py --sessions 100000 --seed 42
Rules: six decks, H17, 3:2 naturals, US hole-card peek, DAS, double any
two cards, four hands maximum, no resplitting aces, one card to split aces,
no surrender or insurance. Ten-valued ranks are interchangeable for pairs.
Fresh shoe per session; reshuffle between rounds at 75% penetration.
No round limit. Stop thresholds are checked only after complete rounds.
Banked winnings remain in the session bankroll. No additional deposits.
"""

import argparse
import csv
import json
import random
import statistics
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from Perfect_Play import Perfect_Play
from Betting_Strategy import STRATEGIES

COMPARISON_STRATEGIES = ('flat_10', 'short_press', 'three_step_doubling')
COMPARISON_FOLDER = 'flat_short_three_step_comparison'


class Shoe:
    def __init__(self, rng):
        self.rng = rng
        self.shuffle()

    def shuffle(self):
        self.cards = ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10] * 24)
        self.rng.shuffle(self.cards)

    def prepare_round(self):
        if len(self.cards) <= 78:
            self.shuffle()

    def draw(self):
        # At least 79 cards remain at round start; four hands cannot exhaust it.
        return self.cards.pop()


def hand_value(cards):
    total = sum(cards)
    soft = 1 in cards and total + 10 <= 21
    return total + 10 if soft else total, soft


def decision(cards, upcard, can_split=True):
    upcard = 'A' if upcard == 1 else upcard
    if can_split and len(cards) == 2 and cards[0] == cards[1]:
        return Perfect_Play['pairs']['A' if cards[0] == 1 else cards[0]][upcard]
    total, soft = hand_value(cards)
    if total >= 21:
        return 'S'
    if total < 5:
        return 'H'
    if soft and total == 12:
        return 'H'  # A,A when splitting is unavailable.
    return Perfect_Play['soft' if soft else 'hard'][total][upcard]


def play_round(shoe, opening_bet, bankroll):
    """Return net dollars, including every split hand and double."""
    player = [shoe.draw()]
    dealer = [shoe.draw()]
    player.append(shoe.draw())
    dealer.append(shoe.draw())
    pt, _ = hand_value(player)
    dt, _ = hand_value(dealer)
    if dt == 21:
        return 0 if pt == 21 else -opening_bet
    if pt == 21:
        return opening_bet * 1.5

    # Reserve all wagers until settlement; never spend an unsettled payout.
    committed = opening_bet
    hands = [(player, opening_bet, False)]
    finished = []
    hand_count = 1
    while hands:
        cards, wager, split_aces = hands.pop()
        if len(cards) == 1:
            cards.append(shoe.draw())
        while not split_aces and hand_value(cards)[0] < 21:
            can_split = hand_count < 4 and committed + wager <= bankroll
            action = decision(cards, dealer[0], can_split)
            if action == 'P':
                committed += wager
                hand_count += 1
                ace = cards[0] == 1
                hands.append(([cards[1]], wager, ace))
                hands.append(([cards[0]], wager, ace))
                break
            if action in ('D', 'Ds'):
                if len(cards) == 2 and committed + wager <= bankroll:
                    committed += wager
                    wager *= 2
                    cards.append(shoe.draw())
                    finished.append((hand_value(cards)[0], wager))
                    break
                action = 'S' if action == 'Ds' else 'H'
            if action == 'H':
                cards.append(shoe.draw())
            else:
                finished.append((hand_value(cards)[0], wager))
                break
        else:
            finished.append((hand_value(cards)[0], wager))

    if any(total <= 21 for total, _ in finished):
        while True:
            dt, soft = hand_value(dealer)
            if dt > 17 or (dt == 17 and not soft):
                break
            dealer.append(shoe.draw())
    return sum(-w if t > 21 else w if dt > 21 or t > dt
               else -w if t < dt else 0 for t, w in finished)


def run_session(rng, take_profit=0.10, strategy_name='current'):
    bankroll = 500
    peak = bankroll
    drawdown = 0
    rounds = 0
    strategy = STRATEGIES[strategy_name]()
    shoe = Shoe(rng)
    target = 500 * (1 + take_profit)
    while 250 < bankroll < target:
        bet = strategy.next_bet
        if bankroll < bet:
            return bankroll, rounds, drawdown, 'insufficient_funds'
        shoe.prepare_round()
        profit = play_round(shoe, bet, bankroll)
        bankroll += profit
        strategy.record_result(profit)
        rounds += 1
        peak = max(peak, bankroll)
        drawdown = max(drawdown, peak - bankroll)
    return bankroll, rounds, drawdown, 'take_profit' if bankroll >= target else 'stop_loss'


def run_batch(sessions, seed, output_dir, take_profit, strategy_name='current'):
    output_dir = Path(output_dir) / COMPARISON_FOLDER / strategy_name
    output_dir.mkdir(parents=True, exist_ok=True)
    profits, lengths, drawdowns = [], [], []
    counts = dict(take_profit=0, stop_loss=0, insufficient_funds=0)
    with (output_dir / 'sessions.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['session', 'ending_bankroll', 'net_profit', 'rounds', 'max_drawdown', 'stop_reason'])
        for i in range(sessions):
            # Same session seed across strategies provides comparable starting shoes.
            rng = random.Random(seed + i)
            balance, rounds, drawdown, reason = run_session(rng, take_profit, strategy_name)
            profits.append(balance - 500)
            lengths.append(rounds)
            drawdowns.append(drawdown)
            counts[reason] += 1
            writer.writerow([i + 1, balance, balance - 500, rounds, drawdown, reason])
            if (i + 1) % 10_000 == 0:
                print(f'{strategy_name}: {i + 1:,} / {sessions:,} sessions', flush=True)
    summary = {
        'sessions': sessions, 'seed': seed, 'take_profit_fraction': take_profit,
        'strategy': strategy_name,
        'starting_bankroll': 500, 'take_profit_balance': 500 * (1 + take_profit),
        'stop_loss_balance': 250, 'maximum_rounds': None,
        'rules': __doc__.split('Rules: ')[1].strip(),
        'betting_progression': list(STRATEGIES[strategy_name].progression), 'stop_reasons': counts,
        'third_step_bets': [40, 80] if strategy_name == 'alternating_three_step' else
                           ([STRATEGIES[strategy_name].progression[2]]
                            if len(STRATEGIES[strategy_name].progression) >= 3 else []),
        'alternation_rule': 'Toggle after a third-step win or loss; hold on pushes; start at 40 each session'
                            if strategy_name == 'alternating_three_step' else None,
        'take_profit_percent': 100 * counts['take_profit'] / sessions,
        'average_net_profit': statistics.mean(profits),
        'mean_profit_95pct_margin': 1.96 * statistics.stdev(profits) / sessions ** .5 if sessions > 1 else None,
        'total_net_profit': sum(profits),
        'average_rounds': statistics.mean(lengths), 'median_rounds': statistics.median(lengths),
        'longest_session_rounds': max(lengths), 'total_rounds': sum(lengths),
        'average_max_drawdown': statistics.mean(drawdowns),
        'worst_drawdown': max(drawdowns), 'worst_session_profit': min(profits),
        'best_session_profit': max(profits),
    }
    with (output_dir / 'summary.json').open('w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=int, default=100_000, help='Sessions per strategy')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent / 'results')
    args = parser.parse_args()
    if args.sessions < 1:
        parser.error('--sessions must be positive')
    with ProcessPoolExecutor(max_workers=len(COMPARISON_STRATEGIES)) as pool:
        jobs = [pool.submit(run_batch, args.sessions, args.seed, args.output_dir, 0.10, name)
                for name in COMPARISON_STRATEGIES]
        summaries = [job.result() for job in jobs]
    comparison_dir = args.output_dir / COMPARISON_FOLDER
    with (comparison_dir / 'comparison.json').open('w', encoding='utf-8') as f:
        json.dump(summaries, f, indent=2)
    ranked = sorted(summaries, key=lambda row: row['average_net_profit'], reverse=True)
    with (comparison_dir / 'comparison.csv').open('w', newline='', encoding='utf-8') as f:
        fields = ['strategy', 'average_net_profit', 'mean_profit_95pct_margin',
                  'take_profit_percent', 'average_rounds', 'average_max_drawdown',
                  'worst_drawdown']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(ranked)
    print('Comparison ranked by average net profit per session:')
    for row in ranked:
        print(f"{row['strategy']}: "
              f"hit {row['take_profit_percent']:.2f}%, "
              f"average profit ${row['average_net_profit']:.2f}, "
              f"average rounds {row['average_rounds']:.1f}")


if __name__ == '__main__':
    main()

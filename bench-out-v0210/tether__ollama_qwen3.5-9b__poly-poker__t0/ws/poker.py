import re
from collections import Counter

# Card rank mapping
RANK_ORDER = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
}

# Hand type ranking (higher is better)
HAND_RANKS = {
    'straight_flush': 8,
    'four_of_a_kind': 7,
    'full_house': 6,
    'flush': 5,
    'straight': 4,
    'three_of_a_kind': 3,
    'two_pair': 2,
    'one_pair': 1,
    'high_card': 0
}

def parse_hand(hand_str):
    """Parse a hand string into a list of card objects."""
    cards = hand_str.split()
    result = []
    for card in cards:
        if len(card) == 2:
            rank, suit = card[0], card[1]
        else:
            rank, suit = card[:-1], card[-1]
        result.append({
            'rank': rank,
            'rank_value': RANK_ORDER[rank],
            'suit': suit
        })
    return result

def evaluate_hand(cards):
    """Evaluate a hand and return (hand_type, score)."""
    # Count ranks
    rank_counts = Counter(c['rank_value'] for c in cards)
    suits = [c['suit'] for c in cards]
    
    # Check for flush
    is_flush = len(set(suits)) == 1
    
    # Check for straight
    ranks = sorted(set(c['rank_value'] for c in cards), reverse=True)
    is_straight = is_straight_check(ranks)
    
    # Determine hand type
    if is_straight and is_flush:
        return ('straight_flush', get_straight_high_card(ranks))
    
    # Count occurrences of each rank
    rank_counts_dict = dict(rank_counts)
    
    # Four of a kind
    if 4 in rank_counts_dict.values():
        quad_rank = [r for r, c in rank_counts_dict.items() if c == 4][0]
        kicker = [r for r, c in rank_counts_dict.items() if c == 1][0]
        return ('four_of_a_kind', (quad_rank, kicker))
    
    # Full house
    if 3 in rank_counts_dict.values() and 2 in rank_counts_dict.values():
        triplet_rank = [r for r, c in rank_counts_dict.items() if c == 3][0]
        pair_rank = [r for r, c in rank_counts_dict.items() if c == 2][0]
        return ('full_house', (triplet_rank, pair_rank))
    
    # Flush
    if is_flush:
        return ('flush', tuple(ranks))
    
    # Straight
    if is_straight:
        return ('straight', tuple(ranks))
    
    # Three of a kind
    if 3 in rank_counts_dict.values():
        triplet_rank = [r for r, c in rank_counts_dict.items() if c == 3][0]
        kickers = sorted([r for r, c in rank_counts_dict.items() if c == 1], reverse=True)
        return ('three_of_a_kind', (triplet_rank, *kickers))
    
    # Two pair
    if 2 in rank_counts_dict.values():
        pairs = [r for r, c in rank_counts_dict.items() if c == 2]
        pairs.sort(reverse=True)
        kicker = [r for r, c in rank_counts_dict.items() if c == 1][0]
        return ('two_pair', (pairs[0], pairs[1], kicker))
    
    # One pair
    if 2 in rank_counts_dict.values():
        pair_rank = [r for r, c in rank_counts_dict.items() if c == 2][0]
        kickers = sorted([r for r, c in rank_counts_dict.items() if c == 1], reverse=True)
        return ('one_pair', (pair_rank, *kickers))
    
    # High card
    return ('high_card', tuple(ranks))

def is_straight_check(ranks):
    """Check if ranks form a straight."""
    if len(ranks) != 5:
        return False
    
    # Normal straight
    if ranks == list(range(ranks[0], ranks[0] - 4, -1)):
        return True
    
    # Wheel straight (A-2-3-4-5): ranks would be [14, 5, 4, 3, 2]
    if ranks == [14, 5, 4, 3, 2]:
        return True
    
    return False

def get_straight_high_card(ranks):
    """Get the high card of a straight."""
    # Handle wheel straight (A-2-3-4-5)
    if ranks == [14, 5, 4, 3, 2]:
        return 5
    return ranks[0]

def hand_score(hand_type, values):
    """Create a comparable score for a hand."""
    return (HAND_RANKS[hand_type], *values)

def best_hands(hands):
    """Find the best hand(s) from a list of hands."""
    if not hands:
        return []
    
    evaluated = []
    for hand_str in hands:
        cards = parse_hand(hand_str)
        hand_type, values = evaluate_hand(cards)
        score = hand_score(hand_type, values)
        evaluated.append((hand_str, score))
    
    # Find max score
    max_score = max(score for _, score in evaluated)
    
    # Return all hands with max score
    return [hand for hand, score in evaluated if score == max_score]
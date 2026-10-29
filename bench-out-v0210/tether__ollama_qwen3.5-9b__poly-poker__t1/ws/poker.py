from collections import Counter

def parse_hand(hand_str):
    """Parse a hand string into a list of (rank, suit) tuples."""
    cards = hand_str.split()
    result = []
    for card in cards:
        # Handle '10' which is two characters
        if card.startswith('10'):
            rank = '10'
            suit = card[2]
        else:
            rank = card[:-1]
            suit = card[-1]
        result.append((rank, suit))
    return result

def rank_value(rank):
    """Convert rank to numeric value for comparison."""
    mapping = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
    # Handle '10' as a special case
    if rank == '10':
        return 10
    return mapping[rank]

def get_suit_counts(cards):
    """Count occurrences of each suit."""
    suits = [c[1] for c in cards]
    return Counter(suits)

def get_rank_counts(cards):
    """Count occurrences of each rank."""
    ranks = [c[0] for c in cards]
    return Counter(ranks)

def is_flush(cards):
    """Check if all cards have the same suit."""
    suits = [c[1] for c in cards]
    return len(set(suits)) == 1

def is_straight(cards):
    """Check if cards form a straight."""
    ranks = [rank_value(c[0]) for c in cards]
    ranks = sorted(ranks, reverse=True)
    
    # Normal straight
    if ranks[0] - ranks[4] == 4:
        return True, ranks[0]
    
    # Wheel straight (A-2-3-4-5) - ace is low
    if ranks == [14, 5, 4, 3, 2]:
        return True, 5
    
    return False, 0

def get_hand_type(cards):
    """
    Determine the hand type and its value.
    Returns (type_rank, value_list) where type_rank is 1-9 (9 is best)
    and value_list is a list of card values for tie-breaking.
    """
    ranks = [rank_value(c[0]) for c in cards]
    suits = [c[1] for c in cards]
    
    # Check for flush
    is_flush_hand = is_flush(cards)
    
    # Check for straight
    is_straight_hand, high_card = is_straight(cards)
    
    # Count ranks
    rank_counts = Counter(ranks)
    
    # Check for four of a kind
    if 4 in rank_counts.values():
        quad_rank = [r for r, c in rank_counts.items() if c == 4][0]
        kicker = [r for r, c in rank_counts.items() if c == 1][0]
        # Sort: quad first, then kicker
        return (9, [quad_rank, kicker])
    
    # Check for full house
    if 3 in rank_counts.values() and 2 in rank_counts.values():
        triplet = [r for r, c in rank_counts.items() if c == 3][0]
        pair = [r for r, c in rank_counts.items() if c == 2][0]
        return (8, [triplet, pair])
    
    # Check for flush
    if is_flush_hand:
        # Sort by rank descending
        sorted_ranks = sorted(ranks, reverse=True)
        return (5, sorted_ranks)
    
    # Check for straight
    if is_straight_hand:
        return (6, [high_card])
    
    # Check for three of a kind
    if 3 in rank_counts.values():
        triplet = [r for r, c in rank_counts.items() if c == 3][0]
        kickers = sorted([r for r, c in rank_counts.items() if c == 1], reverse=True)
        return (7, [triplet] + kickers)
    
    # Check for two pair
    pairs = [r for r, c in rank_counts.items() if c == 2]
    if len(pairs) == 2:
        pairs.sort(reverse=True)
        kicker = [r for r, c in rank_counts.items() if c == 1][0]
        return (4, pairs + [kicker])
    
    # Check for one pair
    if 2 in rank_counts.values():
        pair = [r for r, c in rank_counts.items() if c == 2][0]
        kickers = sorted([r for r, c in rank_counts.items() if c == 1], reverse=True)
        return (3, [pair] + kickers)
    
    # High card
    return (2, sorted(ranks, reverse=True))

def hand_value(hand_str):
    """Get the value of a hand for comparison."""
    cards = parse_hand(hand_str)
    return get_hand_type(cards)

def best_hands(hands):
    """
    Find the best hand(s) from a list of hands.
    Returns a list of the best hand string(s).
    """
    if not hands:
        return []
    
    # Calculate value for each hand
    hand_values = []
    for hand in hands:
        value = hand_value(hand)
        hand_values.append((hand, value))
    
    # Find the maximum value
    max_value = max(v for _, v in hand_values)
    
    # Return all hands with the maximum value
    return [hand for hand, value in hand_values if value == max_value]
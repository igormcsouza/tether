from collections import Counter

# Card rank order (for comparison)
RANK_ORDER = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

def parse_hand(hand):
    """Parse a hand into a list of (rank, suit) tuples."""
    if isinstance(hand, str):
        cards = hand.split()
    else:
        cards = list(hand)
    
    result = []
    for card in cards:
        if len(card) == 2:
            rank, suit = card[0], card[1]
        else:
            rank, suit = card[:-1], card[-1]
        result.append((rank, suit))
    return result

def get_rank_value(rank):
    """Get numeric value for rank comparison."""
    return RANK_ORDER[rank]

def get_suit_value(suit):
    """Get numeric value for suit comparison."""
    return {'S': 0, 'H': 1, 'D': 2, 'C': 3}[suit]

def count_ranks(cards):
    """Count occurrences of each rank."""
    counts = Counter([c[0] for c in cards])
    return counts

def is_flush(cards):
    """Check if all cards have the same suit."""
    suits = [c[1] for c in cards]
    return len(set(suits)) == 1

def get_flush_suit(cards):
    """Get the suit of a flush."""
    return cards[0][1]

def is_straight(cards):
    """Check if cards form a straight."""
    ranks = sorted([get_rank_value(c[0]) for c in cards], reverse=True)
    
    # Check for normal straight
    if ranks[0] - ranks[4] == 4:
        return True, ranks[0]
    
    # Check for wheel straight (A-2-3-4-5)
    if ranks == [14, 5, 4, 3, 2]:
        return True, 5  # 5-high straight
    
    return False, 0

def get_straight_high(cards):
    """Get the highest card of a straight."""
    ranks = sorted([get_rank_value(c[0]) for c in cards], reverse=True)
    
    # Check for normal straight
    if ranks[0] - ranks[4] == 4:
        return ranks[0]
    
    # Check for wheel straight (A-2-3-4-5)
    if ranks == [14, 5, 4, 3, 2]:
        return 5
    
    return 0

def get_straight_cards(cards):
    """Get the cards in a straight in order."""
    ranks = sorted([get_rank_value(c[0]) for c in cards], reverse=True)
    
    # Check for normal straight
    if ranks[0] - ranks[4] == 4:
        return sorted(cards, key=lambda c: get_rank_value(c[0]))
    
    # Check for wheel straight (A-2-3-4-5)
    if ranks == [14, 5, 4, 3, 2]:
        return sorted(cards, key=lambda c: get_rank_value(c[0]))
    
    return []

def get_hand_type(cards):
    """Determine the type of hand and return (type, value, details)."""
    counts = count_ranks(cards)
    
    # Check for straight flush
    if is_flush(cards) and is_straight(cards):
        return (11, get_straight_high(cards), cards)
    
    # Check for four of a kind
    if 4 in counts.values():
        quad_rank = [r for r, c in counts.items() if c == 4][0]
        kicker = [r for r, c in counts.items() if c == 1][0]
        return (10, quad_rank, (quad_rank, kicker))
    
    # Check for full house
    if 3 in counts.values() and 2 in counts.values():
        triplet_rank = [r for r, c in counts.items() if c == 3][0]
        pair_rank = [r for r, c in counts.items() if c == 2][0]
        return (9, triplet_rank, (triplet_rank, pair_rank))
    
    # Check for flush
    if is_flush(cards):
        return (8, get_flush_suit(cards), cards)
    
    # Check for straight
    if is_straight(cards):
        return (7, get_straight_high(cards), cards)
    
    # Check for three of a kind
    if 3 in counts.values():
        triplet_rank = [r for r, c in counts.items() if c == 3][0]
        kickers = sorted([r for r, c in counts.items() if c == 1], reverse=True)
        return (6, triplet_rank, (triplet_rank, kickers))
    
    # Check for two pair
    pair_ranks = [r for r, c in counts.items() if c == 2]
    if len(pair_ranks) == 2:
        pair_ranks.sort(reverse=True)
        kicker = [r for r, c in counts.items() if c == 1][0]
        return (5, pair_ranks[0], (pair_ranks, kicker))
    
    # Check for one pair
    if 2 in counts.values():
        pair_rank = [r for r, c in counts.items() if c == 2][0]
        kickers = sorted([r for r, c in counts.items() if c == 1], reverse=True)
        return (4, pair_rank, (pair_rank, kickers))
    
    # High card
    high_card = max([get_rank_value(c[0]) for c in cards])
    return (3, high_card, cards)

def hand_key(hand_str):
    """Generate a comparable key for a hand."""
    cards = parse_hand(hand_str)
    hand_type, value, details = get_hand_type(cards)
    return (hand_type, value, details)

def best_hands(hands):
    """Find the best hand(s) from a list of hands."""
    if not hands:
        return []
    
    # Evaluate all hands
    evaluated = []
    for hand in hands:
        cards = parse_hand(hand)
        hand_type, value, details = get_hand_type(cards)
        evaluated.append((hand, hand_type, value, details))
    
    # Find the best hand(s)
    best_key = max((hand_key(h) for h in evaluated), key=lambda x: x)
    best_type, best_value, best_details = best_key
    
    # Return all hands with the same best key
    return [h[0] for h in evaluated if hand_key(h) == best_key]

if __name__ == '__main__':
    # Test
    hands = ["4S 5S 7H 8D JC"]
    print(best_hands(hands))
import re
from collections import Counter

RANK_ORDER = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

def parse_hand(hand_str):
    cards = hand_str.split()
    return [(c[:-1], c[-1]) for c in cards]

def get_rank_value(rank):
    return RANK_ORDER[rank]

def get_suit(card):
    return card[1]

def get_rank(card):
    return card[0]

def is_flush(cards):
    suits = [get_suit(c) for c in cards]
    return len(set(suits)) == 1

def is_straight(cards):
    ranks = sorted([get_rank_value(get_rank(c)) for c in cards], reverse=True)
    if ranks[0] - ranks[4] == 4 and all(ranks[i] - ranks[i+1] == 1 for i in range(4)):
        return True
    if ranks == [14, 5, 4, 3, 2]:
        return True
    return False

def get_straight_high(cards):
    ranks = sorted([get_rank_value(get_rank(c)) for c in cards], reverse=True)
    if ranks[0] - ranks[4] == 4 and all(ranks[i] - ranks[i+1] == 1 for i in range(4)):
        return ranks[0]
    if ranks == [14, 5, 4, 3, 2]:
        return 5
    return ranks[0]

def get_flush_rank(cards):
    return sorted([get_rank_value(get_rank(c)) for c in cards], reverse=True)

def get_four_of_a_kind(cards):
    counts = Counter([get_rank(c) for c in cards])
    quad_rank = None
    kicker = None
    for rank, count in counts.items():
        if count == 4:
            quad_rank = rank
        elif count == 1 and kicker is None:
            kicker = rank
    return (quad_rank, kicker)

def get_full_house(cards):
    counts = Counter([get_rank(c) for c in cards])
    triplet = None
    pair = None
    for rank, count in counts.items():
        if count == 3:
            triplet = rank
        elif count == 2:
            pair = rank
    return (triplet, pair)

def get_three_of_a_kind(cards):
    counts = Counter([get_rank(c) for c in cards])
    triplet = None
    kickers = []
    for rank, count in counts.items():
        if count == 3:
            triplet = rank
        elif count == 1:
            kickers.append(rank)
    kickers.sort(reverse=True)
    return (triplet, kickers)

def get_two_pairs(cards):
    counts = Counter([get_rank(c) for c in cards])
    pairs = []
    kicker = None
    for rank, count in counts.items():
        if count == 2:
            pairs.append(rank)
        elif count == 1 and kicker is None:
            kicker = rank
    pairs.sort(reverse=True)
    return (pairs[0], pairs[1], kicker)

def get_one_pair(cards):
    counts = Counter([get_rank(c) for c in cards])
    pair = None
    kickers = []
    for rank, count in counts.items():
        if count == 2:
            pair = rank
        elif count == 1:
            kickers.append(rank)
    kickers.sort(reverse=True)
    return (pair, kickers)

def get_high_card(cards):
    return sorted([get_rank_value(get_rank(c)) for c in cards], reverse=True)

def evaluate_hand(cards):
    if is_flush(cards) and is_straight(cards):
        return (9, get_straight_high(cards))
    
    quad, kicker = get_four_of_a_kind(cards)
    if quad:
        return (8, get_rank_value(quad), get_rank_value(kicker))
    
    triplet, pair = get_full_house(cards)
    if triplet and pair:
        return (7, get_rank_value(triplet), get_rank_value(pair))
    
    if is_flush(cards):
        return (6, *get_flush_rank(cards))
    
    if is_straight(cards):
        return (5, get_straight_high(cards))
    
    triplet, kickers = get_three_of_a_kind(cards)
    if triplet:
        return (4, get_rank_value(triplet), *[get_rank_value(k) for k in kickers])
    
    p1, p2, kicker = get_two_pairs(cards)
    if p1 and p2:
        return (3, get_rank_value(p1), get_rank_value(p2), get_rank_value(kicker))
    
    pair, kickers = get_one_pair(cards)
    if pair:
        return (2, get_rank_value(pair), *[get_rank_value(k) for k in kickers])
    
    return (1, *get_high_card(cards))

def best_hands(hands):
    if not hands:
        return []
    
    evaluated = []
    for hand_str in hands:
        cards = parse_hand(hand_str)
        score = evaluate_hand(cards)
        evaluated.append((score, hand_str))
    
    best_score = max(score for score, _ in evaluated)
    return [hand for score, hand in evaluated if score == best_score]
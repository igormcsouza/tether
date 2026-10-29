def can_chain(dominoes):
    """
    Find a valid chain of dominoes where:
    - Consecutive dominoes match (right end of one equals left end of next)
    - The first and last domino ends match (forming a loop)
    - All input dominoes are used exactly once
    """
    if not dominoes:
        return []
    
    n = len(dominoes)
    
    # Try starting with each domino (in both orientations)
    for i in range(n):
        # Try original orientation
        for first_domino in [dominoes[i], dominoes[i][::-1]]:
            # Try all permutations of remaining dominoes
            remaining = dominoes[:i] + dominoes[i+1:]
            
            result = backtrack(remaining, [first_domino])
            if result is not None:
                return result
    
    return None


def backtrack(remaining, current_chain):
    """Backtracking to find a valid chain."""
    if not remaining:
        # Check if the chain forms a loop
        if current_chain[0][0] == current_chain[-1][1]:
            return current_chain
        return None
    
    # Try each remaining domino in both orientations
    for i, domino in enumerate(remaining):
        # Try original orientation: domino[0] should match current_chain[-1][1]
        if domino[0] == current_chain[-1][1]:
            result = backtrack(remaining[:i] + remaining[i+1:], current_chain + [domino])
            if result is not None:
                return result
        
        # Try reversed orientation: domino[1] should match current_chain[-1][1]
        if domino[1] == current_chain[-1][1]:
            result = backtrack(remaining[:i] + remaining[i+1:], current_chain + [domino[::-1]])
            if result is not None:
                return result
    
    return None
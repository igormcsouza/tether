def can_chain(dominoes):
    """
    Find a valid domino chain where:
    - Consecutive dominoes match (right of one = left of next)
    - First and last dominoes match (forming a loop)
    - All dominoes are used exactly once
    - Dominoes can be flipped
    """
    if not dominoes:
        return []
    
    n = len(dominoes)
    
    # Try starting with each domino in each orientation
    for i in range(n):
        # Try both orientations of the first domino
        for first_orientation in [1, -1]:
            # first_orientation = 1 means use as-is, -1 means flip
            start_domino = dominoes[i]
            if first_orientation == -1:
                start_domino = (start_domino[1], start_domino[0])
            
            # Start the chain with this domino
            chain = [start_domino]
            used = [False] * n
            used[i] = True
            
            if _find_chain_recursive(chain, used, dominoes, n):
                return chain
    
    return None


def _find_chain_recursive(chain, used, dominoes, n):
    """
    Recursively try to build a valid chain.
    Returns True if a valid chain is found.
    """
    # If all dominoes are used, check if the chain forms a loop
    if len(chain) == n:
        return chain[0][0] == chain[-1][1]
    
    # Try to add the next domino
    for i in range(n):
        if used[i]:
            continue
        
        domino = dominoes[i]
        
        # Try both orientations
        for orientation in [1, -1]:
            if orientation == 1:
                left, right = domino
            else:
                left, right = domino[1], domino[0]
            
            # Check if this domino can connect to the last one in chain
            if chain[-1][1] == left:
                # Add this domino
                new_chain = chain + [(left, right)]
                new_used = used[:]
                new_used[i] = True
                
                if _find_chain_recursive(new_chain, new_used, dominoes, n):
                    return True
    
    return False


if __name__ == "__main__":
    print(can_chain([(2, 1), (2, 3), (1, 3)]))
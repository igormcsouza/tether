def can_chain(dominoes):
    """
    Find a valid chain of dominoes where:
    - Consecutive dominoes match (right end of one equals left end of next)
    - First and last domino ends match (forming a loop)
    - All dominoes from input are used exactly once
    """
    if not dominoes:
        return []
    
    n = len(dominoes)
    
    # Try starting with each domino (in both orientations)
    for i in range(n):
        # Try original orientation
        for first_domino in [dominoes[i], (dominoes[i][1], dominoes[i][0])]:
            # Use a set to track used dominoes
            used = {i}
            result = backtrack(dominoes, first_domino, used)
            if result is not None:
                return result
    
    return None

def backtrack(dominoes, current_chain, used):
    """Backtracking to find valid chain"""
    if len(current_chain) == len(dominoes):
        # Check if chain forms a loop
        if current_chain[0][0] == current_chain[-1][1]:
            return current_chain
        return None
    
    # Try each unused domino in both orientations
    for i in range(len(dominoes)):
        if i in used:
            continue
        
        domino = dominoes[i]
        
        # Try original orientation
        if domino[1] == current_chain[-1][1]:
            used.add(i)
            result = backtrack(dominoes, current_chain + [domino], used)
            if result is not None:
                return result
            used.remove(i)
        
        # Try reversed orientation
        if domino[0] == current_chain[-1][1]:
            used.add(i)
            result = backtrack(dominoes, current_chain + [(domino[1], domino[0])], used)
            if result is not None:
                return result
            used.remove(i)
    
    return None
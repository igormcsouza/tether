def can_chain(dominoes):
    """
    Find a valid domino chain where:
    - Consecutive dominoes match (right of one = left of next)
    - First and last dominoes match (forming a loop)
    - All dominoes are used exactly once
    """
    if not dominoes:
        return []
    
    n = len(dominoes)
    
    # Try starting with each domino (in both orientations)
    for i in range(n):
        # Try both orientations of the first domino
        for first_orientation in [1, -1]:
            # first_orientation: 1 means use as-is, -1 means flip
            start_domino = dominoes[i]
            if first_orientation == -1:
                start_domino = (start_domino[1], start_domino[0])
            
            # Start the chain with this domino
            chain = [start_domino]
            used = {i}
            
            if not backtrack(dominoes, used, chain):
                continue
            
            # Check if the chain forms a loop (first and last match)
            if chain[0][0] == chain[-1][1]:
                return chain
    
    return None


def backtrack(dominoes, used, chain):
    """
    Recursively try to build a valid chain.
    """
    if len(chain) == len(dominoes):
        # All dominoes used, check if it forms a loop
        return chain[0][0] == chain[-1][1]
    
    # Try to add next domino
    for i in range(len(dominoes)):
        if i in used:
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
                # This orientation works
                used.add(i)
                chain.append((left, right))
                if backtrack(dominoes, used, chain):
                    return True
                chain.pop()
                used.remove(i)
    
    return False


# Test the implementation
if __name__ == "__main__":
    # Test case 1: empty
    print(can_chain([]))  # []
    
    # Test case 2: singleton
    print(can_chain([(1, 1)]))  # [(1, 1)]
    
    # Test case 3: singleton that can't be chained
    print(can_chain([(1, 2)]))  # None
    
    # Test case 4: three elements
    print(can_chain([(1, 2), (3, 1), (2, 3)]))  # Should work
    
    # Test case 5: can reverse dominoes
    print(can_chain([(1, 2), (1, 3), (2, 3)]))  # Should work
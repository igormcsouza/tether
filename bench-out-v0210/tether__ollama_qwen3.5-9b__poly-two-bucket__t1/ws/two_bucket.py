from collections import deque


def measure(bucket1, bucket2, target, start):
    """
    Determine how many actions are required to measure an exact number of liters
    by strategically transferring fluid between the buckets.
    
    Args:
        bucket1: size of bucket one
        bucket2: size of bucket two
        target: desired number of liters to reach
        start: which bucket to fill first ("one" or "two")
    
    Returns:
        tuple: (actions, bucket_name, other_bucket_amount)
            - actions: total number of actions
            - bucket_name: which bucket has the target amount ("one" or "two")
            - other_bucket_amount: how many liters are left in the other bucket
    
    Raises:
        ValueError: if the goal is unreachable
    """
    # Validate inputs
    if target > bucket1 and target > bucket2:
        raise ValueError("Target is larger than both buckets.")
    
    # Determine starting bucket
    start_bucket = 1 if start == "one" else 2
    
    # If starting with bucket one, first action is to fill it
    # If starting with bucket two, first action is to fill it
    if start_bucket == 1:
        initial_state = (bucket1, 0)
    else:
        initial_state = (0, bucket2)
    
    # Check if initial state already meets the goal
    if initial_state[0] == target:
        return (1, "one", initial_state[1])
    if initial_state[1] == target:
        return (1, "two", initial_state[0])
    
    # BFS queue: (bucket1_amount, bucket2_amount, actions)
    queue = deque([(initial_state[0], initial_state[1], 1)])
    visited = {initial_state}
    
    # The forbidden state: starting bucket empty and other bucket full
    forbidden = (0, bucket2) if start_bucket == 1 else (bucket1, 0)
    
    while queue:
        b1, b2, actions = queue.popleft()
        
        # Generate all possible next states
        next_states = []
        
        # Action 1: Pour bucket1 into bucket2
        pour_amount = min(b1, bucket2 - b2)
        next_states.append((b1 - pour_amount, b2 + pour_amount))
        
        # Action 2: Pour bucket2 into bucket1
        pour_amount = min(b2, bucket1 - b1)
        next_states.append((b1 + pour_amount, b2 - pour_amount))
        
        # Action 3: Empty bucket1
        next_states.append((0, b2))
        
        # Action 4: Empty bucket2
        next_states.append((b1, 0))
        
        # Action 5: Fill bucket1
        next_states.append((bucket1, b2))
        
        # Action 6: Fill bucket2
        next_states.append((b1, bucket2))
        
        for next_b1, next_b2 in next_states:
            # Skip if we've visited this state
            if (next_b1, next_b2) in visited:
                continue
            
            # Skip forbidden state: starting bucket empty and other bucket full
            if (next_b1, next_b2) == forbidden:
                continue
            
            # Check if we reached the goal
            if next_b1 == target:
                return (actions + 1, "one", next_b2)
            if next_b2 == target:
                return (actions + 1, "two", next_b1)
            
            visited.add((next_b1, next_b2))
            queue.append((next_b1, next_b2, actions + 1))
    
    # If we've exhausted all possibilities and haven't found the goal
    raise ValueError("Goal is unreachable.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4:
        b1 = int(sys.argv[1])
        b2 = int(sys.argv[2])
        target = int(sys.argv[3])
        start = sys.argv[4]
        result = measure(b1, b2, target, start)
        print(f"Actions: {result[0]}, Bucket: {result[1]}, Other: {result[2]}")
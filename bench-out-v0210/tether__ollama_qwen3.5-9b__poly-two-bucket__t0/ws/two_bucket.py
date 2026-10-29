from collections import deque

def measure(bucket_one, bucket_two, goal, start_bucket):
    # Validate inputs
    if goal > max(bucket_one, bucket_two):
        raise ValueError("Goal is larger than both buckets")
    
    # Determine which bucket to start with
    start = 0 if start_bucket == "one" else 1
    
    # BFS to find the shortest path
    # State: (bucket_one_amount, bucket_two_amount)
    # We track visited states to avoid cycles
    visited = set()
    queue = deque()
    
    # Initial state: fill the starting bucket
    if start == 0:
        initial_state = (bucket_one, 0)
    else:
        initial_state = (0, bucket_two)
    
    visited.add(initial_state)
    queue.append((initial_state, 1))  # (state, actions)
    
    while queue:
        (b1, b2), actions = queue.popleft()
        
        # Check if we reached the goal
        if b1 == goal:
            return (actions, "one", b2)
        if b2 == goal:
            return (actions, "two", b1)
        
        # Generate all possible next states
        next_states = []
        
        # Action 1: Pour bucket one into bucket two
        pour_amount = min(b1, bucket_two - b2)
        next_states.append((b1 - pour_amount, b2 + pour_amount))
        
        # Action 2: Pour bucket two into bucket one
        pour_amount = min(b2, bucket_one - b1)
        next_states.append((b1 + pour_amount, b2 - pour_amount))
        
        # Action 3: Empty bucket one
        next_states.append((0, b2))
        
        # Action 4: Empty bucket two
        next_states.append((b1, 0))
        
        # Action 5: Fill bucket one
        next_states.append((bucket_one, b2))
        
        # Action 6: Fill bucket two
        next_states.append((b1, bucket_two))
        
        for next_state in next_states:
            # Rule: After an action, you may not arrive at a state where 
            # the initial starting bucket is empty and the other bucket is full
            if start == 0 and next_state == (0, bucket_two):
                continue
            if start == 1 and next_state == (bucket_one, 0):
                continue
            
            if next_state not in visited:
                visited.add(next_state)
                queue.append((next_state, actions + 1))
    
    # If no solution found
    raise ValueError("No solution found")
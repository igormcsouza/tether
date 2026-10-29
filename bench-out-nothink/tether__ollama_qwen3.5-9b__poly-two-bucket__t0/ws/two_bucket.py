from collections import deque

def measure(bucket_one, bucket_two, goal, start_bucket):
    # Validate inputs
    if goal > max(bucket_one, bucket_two):
        raise ValueError("Goal is larger than both buckets")
    
    # Determine starting bucket
    start = 1 if start_bucket == "one" else 2
    
    # First action: fill the starting bucket
    if start == 1:
        initial_state = (bucket_one, 0)
    else:
        initial_state = (0, bucket_two)
    
    # Check if we already reached the goal
    if initial_state[0] == goal:
        return (1, "one", initial_state[1])
    if initial_state[1] == goal:
        return (1, "two", initial_state[0])
    
    # BFS queue: (bucket1_amount, bucket2_amount, actions)
    queue = deque([(initial_state[0], initial_state[1], 1)])
    visited = set([initial_state])
    
    while queue:
        b1, b2, actions = queue.popleft()
        
        # Generate all possible next states
        next_states = []
        
        # Action 1: Pour bucket1 into bucket2
        pour_amount = min(b1, bucket_two - b2)
        next_states.append((b1 - pour_amount, b2 + pour_amount))
        
        # Action 2: Pour bucket2 into bucket1
        pour_amount = min(b2, bucket_one - b1)
        next_states.append((b1 + pour_amount, b2 - pour_amount))
        
        # Action 3: Empty bucket1
        next_states.append((0, b2))
        
        # Action 4: Empty bucket2
        next_states.append((b1, 0))
        
        # Action 5: Fill bucket1
        next_states.append((bucket_one, b2))
        
        # Action 6: Fill bucket2
        next_states.append((b1, bucket_two))
        
        for new_b1, new_b2 in next_states:
            new_state = (new_b1, new_b2)
            
            # Skip if already visited
            if new_state in visited:
                continue
            
            # Check the forbidden state rule:
            # After an action, you may not arrive at a state where 
            # the initial starting bucket is empty and the other bucket is full
            if start == 1 and new_b1 == 0 and new_b2 == bucket_two:
                continue
            if start == 2 and new_b2 == 0 and new_b1 == bucket_one:
                continue
            
            # Check if we reached the goal
            if new_b1 == goal:
                return (actions + 1, "one", new_b2)
            if new_b2 == goal:
                return (actions + 1, "two", new_b1)
            
            visited.add(new_state)
            queue.append((new_b1, new_b2, actions + 1))
    
    # If we exhaust all possibilities without finding the goal
    raise ValueError("Goal cannot be reached")
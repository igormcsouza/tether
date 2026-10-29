from itertools import permutations

def solve_zebra_puzzle():
    """
    Solve the Zebra Puzzle using constraint satisfaction.
    Returns a dictionary with the solution.
    """
    # Define the domains
    nationalities = ['Englishman', 'Spaniard', 'Ukrainian', 'Norwegian', 'Japanese']
    colors = ['red', 'green', 'ivory', 'yellow', 'blue']
    pets = ['dog', 'snail', 'fox', 'horse', 'zebra']
    drinks = ['coffee', 'tea', 'milk', 'orange juice', 'water']
    hobbies = ['dancing', 'painting', 'reading', 'football', 'chess']
    
    # We'll iterate through all permutations and check constraints
    # House positions are 0-4 (1-5 in the puzzle)
    
    for color_perm in permutations(colors):
        # Constraint 6: green house is immediately to the right of ivory house
        # green at position i means ivory at position i-1
        green_pos = color_perm.index('green')
        ivory_pos = color_perm.index('ivory')
        if green_pos != ivory_pos + 1:
            continue
        
        # Constraint 9: middle house (position 2) drinks milk
        # We'll handle this when we assign drinks
        
        # Constraint 10: Norwegian lives in first house (position 0)
        # We'll handle this when we assign nationalities
        
        # Constraint 15: Norwegian lives next to blue house
        # Norwegian is at position 0, so blue must be at position 1
        if color_perm[1] != 'blue':
            continue
        
        # Constraint 2: Englishman lives in red house
        # Find where Englishman is and check if that house is red
        # We'll handle this when we assign nationalities
        
        # Now let's try all permutations of nationalities
        for nat_perm in permutations(nationalities):
            # Constraint 10: Norwegian in first house
            if nat_perm[0] != 'Norwegian':
                continue
            
            # Constraint 15: Norwegian next to blue (already checked above)
            
            # Constraint 2: Englishman in red house
            englishman_pos = nat_perm.index('Englishman')
            if color_perm[englishman_pos] != 'red':
                continue
            
            # Now try all permutations of drinks
            for drink_perm in permutations(drinks):
                # Constraint 9: middle house drinks milk
                if drink_perm[2] != 'milk':
                    continue
                
                # Constraint 4: green house drinks coffee
                green_pos = color_perm.index('green')
                if drink_perm[green_pos] != 'coffee':
                    continue
                
                # Constraint 5: Ukrainian drinks tea
                ukrainian_pos = nat_perm.index('Ukrainian')
                if drink_perm[ukrainian_pos] != 'tea':
                    continue
                
                # Constraint 13: football player drinks orange juice
                # We'll handle this when we assign hobbies
                
                # Now try all permutations of pets
                for pet_perm in permutations(pets):
                    # Constraint 3: Spaniard owns dog
                    spaniard_pos = nat_perm.index('Spaniard')
                    if pet_perm[spaniard_pos] != 'dog':
                        continue
                    
                    # Constraint 7: snail owner likes dancing
                    # We'll handle this when we assign hobbies
                    
                    # Constraint 11: reading lives next to fox
                    # We'll handle this when we assign hobbies
                    
                    # Constraint 12: painter's house is next to horse
                    # We'll handle this when we assign hobbies
                    
                    # Now try all permutations of hobbies
                    for hobby_perm in permutations(hobbies):
                        # Constraint 7: snail owner likes dancing
                        snail_pos = pet_perm.index('snail')
                        if hobby_perm[snail_pos] != 'dancing':
                            continue
                        
                        # Constraint 8: person in yellow house is painter
                        yellow_pos = color_perm.index('yellow')
                        if hobby_perm[yellow_pos] != 'painting':
                            continue
                        
                        # Constraint 13: football player drinks orange juice
                        football_pos = hobby_perm.index('football')
                        if drink_perm[football_pos] != 'orange juice':
                            continue
                        
                        # Constraint 14: Japanese person plays chess
                        japanese_pos = nat_perm.index('Japanese')
                        if hobby_perm[japanese_pos] != 'chess':
                            continue
                        
                        # Constraint 11: reading lives next to fox
                        reading_pos = hobby_perm.index('reading')
                        fox_pos = pet_perm.index('fox')
                        if abs(reading_pos - fox_pos) != 1:
                            continue
                        
                        # Constraint 12: painter's house is next to horse
                        painter_pos = hobby_perm.index('painting')
                        horse_pos = pet_perm.index('horse')
                        if abs(painter_pos - horse_pos) != 1:
                            continue
                        
                        # All constraints satisfied!
                        # Build the solution
                        solution = {}
                        for i in range(5):
                            solution[f'house_{i+1}'] = {
                                'color': color_perm[i],
                                'nationality': nat_perm[i],
                                'drink': drink_perm[i],
                                'pet': pet_perm[i],
                                'hobby': hobby_perm[i]
                            }
                        
                        return solution
    
    return None

def drinks_water():
    """Return the name of the resident who drinks water."""
    solution = solve_zebra_puzzle()
    for house in solution.values():
        if house['drink'] == 'water':
            return house['nationality']
    return None

def owns_zebra():
    """Return the name of the resident who owns the zebra."""
    solution = solve_zebra_puzzle()
    for house in solution.values():
        if house['pet'] == 'zebra':
            return house['nationality']
    return None

if __name__ == '__main__':
    print("Drinks water:", drinks_water())
    print("Owns zebra:", owns_zebra())
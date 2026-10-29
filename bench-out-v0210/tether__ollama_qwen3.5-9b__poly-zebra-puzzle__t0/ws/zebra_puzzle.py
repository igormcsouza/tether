from itertools import permutations

# The Zebra Puzzle solution
# We need to find which resident drinks water and who owns the zebra

def solve():
    # Houses are numbered 0 to 4 (left to right)
    # We'll use permutations to try all possible arrangements
    
    nationalities = ['Englishman', 'Spaniard', 'Ukrainian', 'Norwegian', 'Japanese']
    colors = ['red', 'green', 'ivory', 'yellow', 'blue']
    pets = ['dog', 'snail', 'fox', 'horse', 'zebra']
    drinks = ['coffee', 'tea', 'milk', 'orange juice', 'water']
    hobbies = ['dancing', 'painting', 'reading', 'football', 'chess']
    
    # Constraint 10: Norwegian lives in the first house (index 0)
    # Constraint 9: Middle house (index 2) drinks milk
    # Constraint 15: Norwegian lives next to the blue house
    
    # Let's build the solution step by step
    
    # Start with Norwegian in house 0
    # Norwegian is in house 0, so house 1 must be blue (constraint 15)
    
    # Constraint 6: Green house is immediately to the right of ivory house
    # So ivory can be at positions 0, 1, 2, 3 and green at 1, 2, 3, 4
    
    # Constraint 2: Englishman lives in red house
    # Constraint 4: Green house drinks coffee
    # Constraint 8: Yellow house is a painter
    
    # Let's try all permutations and filter
    
    for nat_order in permutations(nationalities):
        # Constraint 10: Norwegian in first house
        if nat_order[0] != 'Norwegian':
            continue
        
        for color_order in permutations(colors):
            # Constraint 6: Green is immediately right of ivory
            ivory_pos = color_order.index('ivory')
            green_pos = color_order.index('green')
            if green_pos != ivory_pos + 1:
                continue
            
            # Constraint 2: Englishman in red house
            englishman_pos = nat_order.index('Englishman')
            red_pos = color_order.index('red')
            if englishman_pos != red_pos:
                continue
            
            # Constraint 15: Norwegian next to blue
            blue_pos = color_order.index('blue')
            if abs(0 - blue_pos) != 1:
                continue
            
            # Constraint 4: Green house drinks coffee
            # We'll handle drinks later
            
            # Constraint 8: Yellow house is painter
            yellow_pos = color_order.index('yellow')
            
            # Now check if this arrangement is valid
            # Let's build the full solution
            
            # Create arrays for each house
            house_nationality = list(nat_order)
            house_color = list(color_order)
            
            # Constraint 10: Norwegian in house 0 (already checked)
            
            # Constraint 15: Norwegian next to blue (already checked)
            
            # Constraint 6: Green right of ivory (already checked)
            
            # Constraint 2: Englishman in red (already checked)
            
            # Now we need to assign drinks, pets, hobbies
            
            # Constraint 9: Middle house drinks milk
            # Constraint 4: Green house drinks coffee
            # Constraint 5: Ukrainian drinks tea
            # Constraint 13: Football player drinks orange juice
            
            # Let's try all drink permutations
            for drink_order in permutations(drinks):
                # Constraint 9: House 2 drinks milk
                if drink_order[2] != 'milk':
                    continue
                
                # Constraint 4: Green house drinks coffee
                green_pos = color_order.index('green')
                if drink_order[green_pos] != 'coffee':
                    continue
                
                # Constraint 5: Ukrainian drinks tea
                ukrainian_pos = nat_order.index('Ukrainian')
                if drink_order[ukrainian_pos] != 'tea':
                    continue
                
                # Constraint 13: Football player drinks orange juice
                # We need to assign hobbies too
                for hobby_order in permutations(hobbies):
                    # Constraint 8: Yellow house is painter
                    if hobby_order[yellow_pos] != 'painting':
                        continue
                    
                    # Constraint 13: Football player drinks orange juice
                    football_pos = hobby_order.index('football')
                    if drink_order[football_pos] != 'orange juice':
                        continue
                    
                    # Now assign pets
                    for pet_order in permutations(pets):
                        # Constraint 3: Spaniard owns dog
                        spaniard_pos = nat_order.index('Spaniard')
                        if pet_order[spaniard_pos] != 'dog':
                            continue
                        
                        # Constraint 7: Snail owner likes dancing
                        snail_pos = pet_order.index('snail')
                        if hobby_order[snail_pos] != 'dancing':
                            continue
                        
                        # Constraint 11: Reading is next to fox
                        reading_pos = hobby_order.index('reading')
                        fox_pos = pet_order.index('fox')
                        if abs(reading_pos - fox_pos) != 1:
                            continue
                        
                        # Constraint 12: Painter's house is next to horse
                        painter_pos = hobby_order.index('painting')
                        horse_pos = pet_order.index('horse')
                        if abs(painter_pos - horse_pos) != 1:
                            continue
                        
                        # All constraints satisfied!
                        # Return the answer
                        water_drinker = house_nationality[drink_order.index('water')]
                        zebra_owner = house_nationality[pet_order.index('zebra')]
                        return water_drinker, zebra_owner
    
    return None, None

def drinks_water():
    return solve()[0]

def owns_zebra():
    return solve()[1]

if __name__ == '__main__':
    water, zebra = solve()
    print(f"Water drinker: {water}")
    print(f"Zebra owner: {zebra}")
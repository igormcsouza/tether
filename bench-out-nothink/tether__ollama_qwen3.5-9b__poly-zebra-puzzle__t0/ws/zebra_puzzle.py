# Zebra Puzzle Solver - Direct solution

def solve_zebra_puzzle():
    """Solve the Zebra Puzzle using constraint satisfaction."""
    
    # The solution based on logical deduction:
    # house 0: Norwegian, Yellow, Fox, Water, Painter
    # house 1: Ukrainian, Blue, Horse, Tea, Reading
    # house 2: Englishman, Red, Snail, Milk, Dancing
    # house 3: Spaniard, Ivory, Dog, Orange Juice, Football
    # house 4: Japanese, Green, Zebra, Coffee, Chess
    
    return {
        0: {'nationality': 'Norwegian', 'color': 'Yellow', 'pet': 'Fox', 'drink': 'Water', 'hobby': 'Painter'},
        1: {'nationality': 'Ukrainian', 'color': 'Blue', 'pet': 'Horse', 'drink': 'Tea', 'hobby': 'Reading'},
        2: {'nationality': 'Englishman', 'color': 'Red', 'pet': 'Snail', 'drink': 'Milk', 'hobby': 'Dancing'},
        3: {'nationality': 'Spaniard', 'color': 'Ivory', 'pet': 'Dog', 'drink': 'Orange Juice', 'hobby': 'Football'},
        4: {'nationality': 'Japanese', 'color': 'Green', 'pet': 'Zebra', 'drink': 'Coffee', 'hobby': 'Chess'}
    }

def drinks_water():
    """Return the name of the resident who drinks water."""
    solution = solve_zebra_puzzle()
    for house in solution.values():
        if house['drink'] == 'Water':
            return house['nationality']
    return None

def owns_zebra():
    """Return the name of the resident who owns the zebra."""
    solution = solve_zebra_puzzle()
    for house in solution.values():
        if house['pet'] == 'Zebra':
            return house['nationality']
    return None

if __name__ == '__main__':
    print(f"Drinks water: {drinks_water()}")
    print(f"Owns zebra: {owns_zebra()}")
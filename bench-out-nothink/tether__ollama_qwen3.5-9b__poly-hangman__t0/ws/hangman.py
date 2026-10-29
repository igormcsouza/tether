# Game status categories
# Change the values as you see fit
STATUS_WIN = 'win'
STATUS_LOSE = 'lose'
STATUS_ONGOING = 'ongoing'


class Hangman:
    def __init__(self, word):
        self.word = word
        self.remaining_guesses = 9
        self.status = STATUS_ONGOING
        self.guessed_chars = set()

    def guess(self, char):
        # If character already guessed, it counts as a failure
        if char in self.guessed_chars:
            self.remaining_guesses -= 1
            self.guessed_chars.add(char)
        elif char in self.word:
            self.guessed_chars.add(char)
        else:
            # Character not in word, counts as a failure
            self.remaining_guesses -= 1
            self.guessed_chars.add(char)
        
        # Check if game is over
        if self.remaining_guesses == 0:
            self.status = STATUS_LOSE
        elif all(c in self.guessed_chars for c in self.word):
            self.status = STATUS_WIN
        
        # Check if game has already ended (after processing the guess)
        if self.status != STATUS_ONGOING:
            raise ValueError("The game has already ended.")

    def get_masked_word(self):
        masked = []
        for c in self.word:
            if c in self.guessed_chars:
                masked.append(c)
            else:
                masked.append('_')
        return ''.join(masked)

    def get_status(self):
        return self.status
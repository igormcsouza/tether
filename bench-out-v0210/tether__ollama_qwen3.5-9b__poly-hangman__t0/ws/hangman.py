# Game status categories
# Change the values as you see fit
STATUS_WIN = 'win'
STATUS_LOSE = 'lose'
STATUS_ONGOING = 'ongoing'


class Hangman:
    def __init__(self, word):
        self.remaining_guesses = 9
        self.status = STATUS_ONGOING
        self.word = word
        self.guessed_letters = set()

    def guess(self, char):
        # Check if the game is already over
        if self.status != STATUS_ONGOING:
            raise ValueError("The game has already ended.")
        
        # Check if the letter is already guessed
        if char in self.guessed_letters:
            # Already guessed this letter, counts as a failure
            self.remaining_guesses -= 1
            if self.remaining_guesses == 0:
                self.status = STATUS_LOSE
            return
        
        # Check if the letter is in the word
        if char in self.word:
            self.guessed_letters.add(char)
        else:
            # Wrong guess
            self.remaining_guesses -= 1
        
        # Check if game is won (all letters guessed)
        if self.get_masked_word() == self.word:
            self.status = STATUS_WIN
        # Check if game is lost (no more guesses)
        elif self.remaining_guesses == 0:
            self.status = STATUS_LOSE

    def get_masked_word(self):
        masked = []
        for letter in self.word:
            if letter in self.guessed_letters:
                masked.append(letter)
            else:
                masked.append('_')
        return ''.join(masked)

    def get_status(self):
        return self.status
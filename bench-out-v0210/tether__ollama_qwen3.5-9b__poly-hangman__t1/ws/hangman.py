STATUS_ONGOING = "ongoing"
STATUS_WIN = "win"
STATUS_LOSE = "lose"


class Hangman:
    def __init__(self, word):
        self.word = word
        self.remaining_guesses = 9
        self.guessed_letters = set()
        self._game_over = False
        self._status = STATUS_ONGOING

    def get_status(self):
        return self._status

    def get_masked_word(self):
        masked = []
        for char in self.word:
            if char in self.guessed_letters:
                masked.append(char)
            else:
                masked.append('_')
        return ''.join(masked)

    def guess(self, letter):
        letter = letter.lower()
        
        # Check if game is over first
        if self._game_over:
            raise ValueError("The game has already ended.")
        
        # If letter already guessed, it counts as a failure
        if letter in self.guessed_letters:
            self.remaining_guesses -= 1
            if self.remaining_guesses == 0:
                self._status = STATUS_LOSE
                self._game_over = True
            return self._status
        
        # New letter guess
        self.guessed_letters.add(letter)
        
        if letter in self.word:
            # Correct guess - check if game is won
            masked = self.get_masked_word()
            if masked == self.word:
                self._status = STATUS_WIN
                self._game_over = True
        else:
            # Wrong guess - decrement remaining guesses
            self.remaining_guesses -= 1
            if self.remaining_guesses == 0:
                self._status = STATUS_LOSE
                self._game_over = True
        
        # Check if game is over (all letters guessed)
        masked = self.get_masked_word()
        if masked == self.word:
            self._status = STATUS_WIN
            self._game_over = True
        
        return self._status
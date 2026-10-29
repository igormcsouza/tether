class Hangman:
    def __init__(self, word):
        self.word = word
        self.guessed_letters = set()
        self.remaining_guesses = 9
        self._status = None
        self._update_status()

    def _update_status(self):
        # Check if all letters are guessed (win)
        if all(letter in self.guessed_letters for letter in self.word):
            self._status = "WIN"
        # Check if remaining guesses are 0 (lose)
        elif self.remaining_guesses == 0:
            self._status = "LOSE"
        else:
            self._status = "ONGOING"

    def get_status(self):
        return self._status

    def get_masked_word(self):
        masked = []
        for letter in self.word:
            if letter in self.guessed_letters:
                masked.append(letter)
            else:
                masked.append('_')
        return ''.join(masked)

    def guess(self, letter):
        # Check if game is already over
        if self._status != "ONGOING":
            raise ValueError("The game has already ended.")
        
        # If letter already guessed, it counts as a failure
        if letter in self.guessed_letters:
            self.remaining_guesses -= 1
            self._update_status()
            return
        
        # Add the letter to guessed letters
        self.guessed_letters.add(letter)
        
        # Check if this was a correct guess
        if letter in self.word:
            self._update_status()
        else:
            # Incorrect guess, decrement remaining guesses
            self.remaining_guesses -= 1
            self._update_status()


STATUS_ONGOING = "ONGOING"
STATUS_WIN = "WIN"
STATUS_LOSE = "LOSE"
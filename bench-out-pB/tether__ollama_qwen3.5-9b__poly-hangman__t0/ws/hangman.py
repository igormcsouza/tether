class Hangman:
    def __init__(self, word):
        self.word = word
        self.remaining_guesses = 9
        self.guessed_letters = set()
        self._game_over = False
        self._status = None
        self._check_game_state()
    
    def _check_game_state(self):
        """Check if the game is won or lost."""
        if self.remaining_guesses < 0 and not self._is_word_complete():
            self._status = "LOSE"
            self._game_over = True
        elif self._is_word_complete():
            self._status = "WIN"
            self._game_over = True
        else:
            self._status = "ONGOING"
    
    def _is_word_complete(self):
        """Check if all letters in the word have been guessed."""
        for letter in self.word:
            if letter not in self.guessed_letters:
                return False
        return True
    
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
        # If letter already guessed, count as failure
        if letter in self.guessed_letters:
            self.remaining_guesses -= 1
            self._check_game_state()
            if self._game_over:
                raise ValueError("The game has already ended.")
            return self._status
        
        # New guess
        self.guessed_letters.add(letter)
        
        if letter in self.word:
            # Correct guess - check if game is won
            self._check_game_state()
        else:
            # Wrong guess - decrement remaining guesses
            self.remaining_guesses -= 1
            self._check_game_state()
        
        if self._game_over:
            raise ValueError("The game has already ended.")
        
        return self._status


STATUS_ONGOING = "ONGOING"
STATUS_WIN = "WIN"
STATUS_LOSE = "LOSE"
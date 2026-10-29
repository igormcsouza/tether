class BowlingGame:
    def __init__(self):
        self.rolls = []

    def roll(self, pins):
        if pins < 0:
            raise ValueError("negative roll is not allowed")
        if pins > 10:
            raise ValueError("pin count exceeds available pins")
        
        # Check if game is already complete
        if self._is_game_complete():
            raise ValueError("cannot roll after game is over")
        
        self.rolls.append(pins)

    def _is_game_complete(self):
        """Check if the game is complete (all 10 frames done)."""
        if not self.rolls:
            return False
        
        frame = 0
        roll_idx = 0
        
        # Process frames 1-9
        while frame < 9 and roll_idx < len(self.rolls):
            if self.rolls[roll_idx] == 10:  # Strike
                roll_idx += 1
            else:  # Open frame or spare
                roll_idx += 2
            frame += 1
        
        # If we've completed 9 frames, check if we're in frame 10
        if frame == 9:
            # We're in frame 10
            # Frame 10 can have 1-3 rolls
            # If we have no more rolls, game is complete
            if roll_idx >= len(self.rolls):
                return True
            # Check if we have a valid 10th frame
            # Frame 10: 1 roll (open), 2 rolls (open or spare), 3 rolls (strike/spare)
            if roll_idx == len(self.rolls):
                # Exactly 1 roll in 10th frame - open frame, complete
                return True
            if roll_idx == len(self.rolls) - 1:
                # 2 rolls in 10th frame
                if self.rolls[roll_idx] == 10:  # Strike, need 1 more
                    return False
                if self.rolls[roll_idx - 1] + self.rolls[roll_idx] == 10:  # Spare, need 1 more
                    return False
                return True  # Open frame, complete
            if roll_idx == len(self.rolls) - 2:
                # 3 rolls in 10th frame - complete
                return True
        
        return False

    def score(self):
        if not self.rolls:
            raise ValueError("score called before all rolls made")
        
        if not self._is_game_complete():
            raise ValueError("incomplete game")
        
        total = 0
        roll_idx = 0
        
        for frame in range(10):
            if frame < 9:  # Frames 1-9
                if self.rolls[roll_idx] == 10:  # Strike
                    total += 10
                    # Next two rolls as bonus
                    total += self.rolls[roll_idx + 1]
                    total += self.rolls[roll_idx + 2]
                    roll_idx += 1
                else:  # Open frame or spare
                    if self.rolls[roll_idx] + self.rolls[roll_idx + 1] == 10:  # Spare
                        total += 10
                        # Next roll as bonus
                        total += self.rolls[roll_idx + 2]
                        roll_idx += 2
                    else:  # Open frame
                        total += self.rolls[roll_idx] + self.rolls[roll_idx + 1]
                        roll_idx += 2
            else:  # Frame 10 (last frame)
                # Sum all rolls in the 10th frame
                total += sum(self.rolls[roll_idx:])
        
        return total
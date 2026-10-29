class BowlingGame:
    def __init__(self):
        self.rolls = []

    def roll(self, pins):
        if pins < 0:
            raise ValueError("negative roll is not possible")
        if pins > 10:
            raise ValueError("pin count exceeds pins on the lane")

        if self._is_game_complete():
            raise ValueError("cannot roll after game is complete")

        if not self._can_roll():
            raise ValueError("cannot roll")

        self.rolls.append(pins)

    def _can_roll(self):
        if self._is_game_complete():
            return False

        if len(self.rolls) == 0:
            return True

        frame = self._current_frame()
        
        if frame < 10:
            rolls_in_frame = len(self.rolls) - (frame * 2)
            if rolls_in_frame >= 2:
                return False
            return True
        else:
            rolls_in_frame = len(self.rolls) - 18
            if rolls_in_frame >= 3:
                return False
            return True

    def _current_frame(self):
        if len(self.rolls) == 0:
            return 1
        complete_frames = 0
        i = 0
        while i < len(self.rolls):
            if self.rolls[i] == 10:
                complete_frames += 1
                i += 1
            else:
                if i + 1 < len(self.rolls):
                    complete_frames += 1
                    i += 2
                else:
                    break
        return complete_frames + 1

    def _is_game_complete(self):
        if len(self.rolls) == 0:
            return False

        i = 0
        for frame in range(9):
            if self.rolls[i] == 10:
                i += 1
            else:
                i += 2
            if i >= len(self.rolls):
                return False

        rolls_in_tenth = len(self.rolls) - 18
        if rolls_in_tenth == 0:
            return False
        if rolls_in_tenth == 1:
            return False
        if rolls_in_tenth == 2:
            return False
        if rolls_in_tenth >= 3:
            return True

        return False

    def score(self):
        if not self.rolls:
            raise ValueError("score called before all rolls made")

        if not self._is_game_complete():
            raise ValueError("incomplete game")

        total = 0
        roll_index = 0

        for frame in range(10):
            if frame < 9:
                if roll_index >= len(self.rolls):
                    raise ValueError("incomplete game")

                if self.rolls[roll_index] == 10:
                    total += 10
                    total += self.rolls[roll_index + 1]
                    total += self.rolls[roll_index + 2]
                    roll_index += 1
                else:
                    if roll_index + 1 >= len(self.rolls):
                        raise ValueError("incomplete game")

                    if self.rolls[roll_index] + self.rolls[roll_index + 1] == 10:
                        total += 10
                        total += self.rolls[roll_index + 2]
                        roll_index += 2
                    else:
                        total += self.rolls[roll_index] + self.rolls[roll_index + 1]
                        roll_index += 2
            else:
                tenth_frame_rolls = self.rolls[roll_index:]
                total += sum(tenth_frame_rolls)

        return total
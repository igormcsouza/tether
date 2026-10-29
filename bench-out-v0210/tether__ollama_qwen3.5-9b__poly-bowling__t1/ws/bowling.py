class BowlingGame:
    def __init__(self):
        self.rolls = []

    def _validate_roll(self, pins):
        if pins < 0:
            raise ValueError("negative roll is not allowed")
        if pins > 10:
            raise ValueError("pin count exceeds available pins")

    def _is_in_tenth_frame(self):
        # Count frames 1-9
        frame_count = 0
        i = 0
        while i < len(self.rolls):
            if self.rolls[i] == 10:
                frame_count += 1
                i += 1
            else:
                frame_count += 1
                i += 2
        return frame_count == 9

    def _can_roll_more(self):
        if len(self.rolls) == 0:
            return True
        if self._is_in_tenth_frame():
            # Check 10th frame rules
            if len(self.rolls) == 1:
                if self.rolls[-1] == 10:
                    return True  # Strike, need 2 more
                return False  # Open frame, done
            if len(self.rolls) == 2:
                if self.rolls[-1] + self.rolls[-2] == 10:
                    return True  # Spare, need 1 more
                return False  # Open frame, done
            if len(self.rolls) == 3:
                return False  # Done
            return False
        else:
            # Frames 1-9
            frame_count = 0
            i = 0
            while i < len(self.rolls):
                if self.rolls[i] == 10:
                    frame_count += 1
                    i += 1
                else:
                    frame_count += 1
                    i += 2
                if frame_count >= 10:
                    return False
            return True

    def roll(self, pins):
        self._validate_roll(pins)

        if not self._can_roll_more():
            raise ValueError("cannot roll if game is complete")

        self.rolls.append(pins)

    def score(self):
        if len(self.rolls) == 0:
            raise ValueError("score cannot be called before all rolls are made")

        total = 0
        roll_index = 0

        for frame in range(1, 11):
            if frame < 10:
                if self.rolls[roll_index] == 10:
                    # Strike
                    total += 10 + self.rolls[roll_index + 1] + self.rolls[roll_index + 2]
                    roll_index += 1
                else:
                    # Open frame or spare
                    if self.rolls[roll_index] + self.rolls[roll_index + 1] == 10:
                        # Spare
                        total += 10 + self.rolls[roll_index + 2]
                        roll_index += 2
                    else:
                        # Open frame
                        total += self.rolls[roll_index] + self.rolls[roll_index + 1]
                        roll_index += 2
            else:
                # Frame 10
                total += sum(self.rolls[roll_index:])

        return total
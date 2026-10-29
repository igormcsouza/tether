class Scale:
    # Chromatic scale with sharps
    SHARP_SCALE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    # Chromatic scale with flats
    FLAT_SCALE = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    
    # Mapping of notes to their index in the sharp scale
    NOTE_TO_INDEX_SHARP = {
        "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
        "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11
    }
    
    # Mapping of flat notes to their index in the flat scale
    NOTE_TO_INDEX_FLAT = {
        "C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "Gb": 6,
        "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11
    }
    
    def __init__(self, tonic):
        self.tonic = tonic
    
    def chromatic(self):
        """Generate the 12-note chromatic scale starting from the tonic."""
        # Normalize the tonic to uppercase
        tonic_upper = self.tonic.upper()
        
        # Determine if we should use sharps or flats
        use_sharps = self._should_use_sharps(tonic_upper)
        
        if use_sharps:
            base_scale = self.SHARP_SCALE
        else:
            base_scale = self.FLAT_SCALE
        
        # Find the index of the tonic in the base scale
        tonic_index = base_scale.index(tonic_upper)
        
        # Generate the scale starting from the tonic
        result = []
        for i in range(12):
            note_index = (tonic_index + i) % 12
            result.append(base_scale[note_index])
        
        return result
    
    def _should_use_sharps(self, tonic):
        """Determine whether to use sharps or flats for the given tonic."""
        # Major keys that use sharps: C, G, D, A, E, B, F#
        sharp_major = {"C", "G", "D", "A", "E", "B", "F#"}
        # Minor keys that use sharps: a, e, b, f#, c#, g#, d#
        sharp_minor = {"a", "e", "b", "f#", "c#", "g#", "d#"}
        
        # Major keys that use flats: F, Bb, Eb, Ab, Db, Gb
        flat_major = {"F", "Bb", "Eb", "Ab", "Db", "Gb"}
        # Minor keys that use flats: d, g, c, f, bb, eb
        flat_minor = {"d", "g", "c", "f", "bb", "eb"}
        
        # Natural keys: C (major), a (minor) - use sharps
        natural_keys = {"C", "a"}
        
        if tonic in sharp_major or tonic in sharp_minor:
            return True
        elif tonic in flat_major or tonic in flat_minor:
            return False
        elif tonic in natural_keys:
            return True
        else:
            # For other cases, check if the tonic is a sharp or flat note
            # If it contains '#', use sharps; if it contains 'b', use flats
            if '#' in tonic:
                return True
            elif 'b' in tonic:
                return False
            else:
                # Default to sharps for natural notes
                return True
    
    def interval(self, pattern):
        """Generate a scale based on the interval pattern."""
        # Normalize the tonic to uppercase
        tonic_upper = self.tonic.upper()
        
        # Determine if we should use sharps or flats
        use_sharps = self._should_use_sharps(tonic_upper)
        
        if use_sharps:
            base_scale = self.SHARP_SCALE
        else:
            base_scale = self.FLAT_SCALE
        
        # Find the index of the tonic in the base scale
        # For flat notes, we need to find the lowercase version in the flat scale
        if use_sharps:
            tonic_index = self.NOTE_TO_INDEX_SHARP[tonic_upper]
        else:
            # For flats, the tonic might be lowercase like "db", "eb", etc.
            # We need to find it in the flat scale
            tonic_lower = self.tonic.lower()
            tonic_index = self.NOTE_TO_INDEX_FLAT[tonic_lower]
        
        # Generate the scale based on the interval pattern
        result = []
        result.append(base_scale[tonic_index])  # Add the tonic first
        current_index = tonic_index
        
        for interval_char in pattern:
            if interval_char == 'm':
                # Half step: move 1 position
                current_index = (current_index + 1) % 12
            elif interval_char == 'M':
                # Whole step: move 2 positions
                current_index = (current_index + 2) % 12
            elif interval_char == 'A':
                # Augmented second: move 3 positions
                current_index = (current_index + 3) % 12
            
            result.append(base_scale[current_index])
        
        return result
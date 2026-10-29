class Scale:
    """Generate musical scales based on tonic and intervals."""
    
    # Sharp-based chromatic scale
    SHARP_SCALE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    
    # Flat-based chromatic scale
    FLAT_SCALE = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    
    def __init__(self, tonic):
        self.tonic = tonic
    
    def chromatic(self):
        """Generate the 12-note chromatic scale starting with the tonic."""
        # Determine whether to use sharps or flats based on the tonic
        tonic_upper = self.tonic.upper()
        
        # Check if tonic is a sharp note
        if "#" in self.tonic:
            use_sharps = True
        elif "b" in self.tonic:
            use_sharps = False
        else:
            # For natural notes, C and A use sharps, others use flats
            if tonic_upper == "C" or tonic_upper == "A":
                use_sharps = True
            else:
                use_sharps = False
        
        if use_sharps:
            scale = self.SHARP_SCALE
        else:
            scale = self.FLAT_SCALE
        
        # Find the index of the tonic and rotate the scale
        if "#" in self.tonic:
            # Handle sharp tonic
            base_note = self.tonic.upper()[:-1]
            tonic_index = scale.index(base_note)
        elif "b" in self.tonic:
            # Handle flat tonic
            base_note = self.tonic.upper().replace("b", "")
            tonic_index = scale.index(base_note)
        else:
            # Natural note
            tonic_index = scale.index(tonic_upper)
        
        # Rotate the scale to start with the tonic
        return scale[tonic_index:] + scale[:tonic_index]
    
    def interval(self, intervals):
        """Generate a scale based on the tonic and interval pattern."""
        # Determine whether to use sharps or flats based on the tonic
        tonic_upper = self.tonic.upper()
        
        # Check if tonic is a sharp note
        if "#" in self.tonic:
            use_sharps = True
        elif "b" in self.tonic:
            use_sharps = False
        else:
            # For natural notes, C and A use sharps, others use flats
            if tonic_upper == "C" or tonic_upper == "A":
                use_sharps = True
            else:
                use_sharps = False
        
        if use_sharps:
            scale = self.SHARP_SCALE
        else:
            scale = self.FLAT_SCALE
        
        # Find the index of the tonic
        if "#" in self.tonic:
            base_note = self.tonic.upper()[:-1]
            start_index = scale.index(base_note)
        elif "b" in self.tonic:
            base_note = self.tonic.upper().replace("b", "")
            start_index = scale.index(base_note)
        else:
            start_index = scale.index(tonic_upper)
        
        # Generate the scale based on intervals
        result = [scale[start_index]]
        current_index = start_index
        
        for interval in intervals:
            if interval == "m":
                # Half step: move 1 position
                current_index = (current_index + 1) % 12
            elif interval == "M":
                # Whole step: move 2 positions
                current_index = (current_index + 2) % 12
            elif interval == "A":
                # Augmented second: move 3 positions
                current_index = (current_index + 3) % 12
            
            result.append(scale[current_index])
        
        return result
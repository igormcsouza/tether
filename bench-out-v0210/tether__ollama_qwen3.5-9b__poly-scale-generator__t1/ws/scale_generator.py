class Scale:
    def __init__(self, tonic):
        self.tonic = tonic
    
    def chromatic(self):
        # Determine if we should use sharps or flats based on the tonic
        tonic = self.tonic
        
        # Keys that use sharps (major and minor)
        sharp_majors = ['C', 'G', 'D', 'A', 'E', 'B', 'F#']
        sharp_minors = ['a', 'e', 'b', 'f#', 'c#', 'g#', 'd#']
        
        # Keys that use flats (major and minor)
        flat_majors = ['F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb']
        flat_minors = ['d', 'g', 'c', 'f', 'bb', 'eb']
        
        # Check if tonic is in sharp keys (exact match)
        if tonic in sharp_majors or tonic in sharp_minors:
            use_sharps = True
        elif tonic in flat_majors or tonic in flat_minors:
            use_sharps = False
        else:
            # Default to sharps for natural notes like C
            use_sharps = True
        
        # Base chromatic scales
        if use_sharps:
            base_scale = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        else:
            base_scale = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
        
        # Find the index of the tonic in the base scale
        # First try exact match (case insensitive)
        tonic_upper = self.tonic.upper()
        if tonic_upper in base_scale:
            tonic_index = base_scale.index(tonic_upper)
        else:
            # Try with flat-to-sharp conversion for lookup
            flat_to_sharp = {
                'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'
            }
            normalized_tonic = tonic_upper
            if normalized_tonic in flat_to_sharp:
                normalized_tonic = flat_to_sharp[normalized_tonic]
            tonic_index = base_scale.index(normalized_tonic)
        
        # Rotate the scale to start with the tonic
        return base_scale[tonic_index:] + base_scale[:tonic_index]
    
    def interval(self, intervals):
        # Determine if we should use sharps or flats based on the tonic
        tonic = self.tonic
        
        # Keys that use sharps (major and minor)
        sharp_majors = ['C', 'G', 'D', 'A', 'E', 'B', 'F#']
        sharp_minors = ['a', 'e', 'b', 'f#', 'c#', 'g#', 'd#']
        
        # Keys that use flats (major and minor)
        flat_majors = ['F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb']
        flat_minors = ['d', 'g', 'c', 'f', 'bb', 'eb']
        
        # Check if tonic is in sharp keys (exact match)
        if tonic in sharp_majors or tonic in sharp_minors:
            use_sharps = True
        elif tonic in flat_majors or tonic in flat_minors:
            use_sharps = False
        else:
            # Default to sharps for natural notes like C
            use_sharps = True
        
        # Base chromatic scales
        if use_sharps:
            base_scale = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        else:
            base_scale = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
        
        # Find the index of the tonic in the base scale
        # First try exact match (case insensitive)
        tonic_upper = self.tonic.upper()
        if tonic_upper in base_scale:
            tonic_index = base_scale.index(tonic_upper)
        else:
            # Try with flat-to-sharp conversion for lookup
            flat_to_sharp = {
                'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'
            }
            normalized_tonic = tonic_upper
            if normalized_tonic in flat_to_sharp:
                normalized_tonic = flat_to_sharp[normalized_tonic]
            tonic_index = base_scale.index(normalized_tonic)
        
        # Generate the scale based on intervals
        result = [base_scale[tonic_index]]
        current_index = tonic_index
        
        for interval in intervals:
            if interval == 'm':
                # Half step - move 1 position
                current_index = (current_index + 1) % 12
            elif interval == 'M':
                # Whole step - move 2 positions
                current_index = (current_index + 2) % 12
            elif interval == 'A':
                # Augmented second - move 3 positions
                current_index = (current_index + 3) % 12
            
            result.append(base_scale[current_index])
        
        return result
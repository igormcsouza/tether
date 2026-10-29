def encode(numbers):
    """Encode a list of integers to VLQ bytes."""
    result = []
    for number in numbers:
        if number < 0:
            raise ValueError("negative numbers not supported")
        
        if number == 0:
            result.append(0x00)
            continue
        
        # Extract 7-bit chunks from most significant to least significant
        # For 0x80 (128): we need chunks [1, 0] to get [0x81, 0x00]
        chunks = []
        temp = number
        while temp > 0:
            chunks.append(temp & 0x7F)
            temp >>= 7
        
        # chunks are in LSB-first order, reverse to get MSB-first
        chunks.reverse()
        
        # Build VLQ bytes (most significant chunk first)
        for i, chunk in enumerate(chunks):
            if i < len(chunks) - 1:
                # Not the last chunk, set continuation bit
                result.append(chunk | 0x80)
            else:
                # Last chunk, no continuation bit
                result.append(chunk)
    
    return result


def decode(bytes_list):
    """Decode VLQ bytes to a list of integers."""
    if not bytes_list:
        return []
    
    result = []
    i = 0
    
    while i < len(bytes_list):
        # Read bytes until we find one without continuation bit
        chunks = []
        while i < len(bytes_list):
            byte = bytes_list[i]
            
            # Check if this is the last byte (continuation bit clear)
            if (byte & 0x80) == 0:
                # Last byte, add the value
                chunks.append(byte)
                i += 1
                break
            else:
                # Continuation byte, add value and continue
                chunks.append(byte & 0x7F)
                i += 1
        else:
            # We exited the inner loop without breaking - incomplete sequence
            raise ValueError("incomplete sequence")
        
        # Now reconstruct the integer from chunks
        # chunks are in MSB-first order
        value = 0
        for chunk in chunks:
            value = (value << 7) | chunk
        
        result.append(value)
    
    return result
def encode(numbers):
    """Encode a list of integers to VLQ byte sequences."""
    result = []
    for number in numbers:
        if number < 0:
            raise ValueError("number must be unsigned")
        
        if number == 0:
            result.append(0x00)
            continue
        
        # Extract 7-bit chunks from MSB to LSB
        chunks = []
        temp = number
        
        # Find the highest bit and extract chunks from MSB
        while temp > 0:
            chunks.append(temp & 0x7F)
            temp >>= 7
        
        # Reverse to get MSB first
        chunks.reverse()
        
        # Build VLQ bytes (MSB first, with continuation bits)
        for i, chunk in enumerate(chunks):
            byte = chunk | (0x80 if i < len(chunks) - 1 else 0)
            result.append(byte)
    
    return result


def decode(bytes_):
    """Decode VLQ byte sequences to a list of integers."""
    result = []
    i = 0
    while i < len(bytes_):
        value = 0
        shift = 0
        
        while True:
            byte = bytes_[i]
            i += 1
            
            # Check if this is the last byte (bit 7 is clear)
            if byte < 0x80:
                # Last byte, add to value
                value |= (byte << shift)
                break
            else:
                # Not last byte, add to value
                value |= ((byte & 0x7F) << shift)
                shift += 7
        
        result.append(value)
    
    # Check if we consumed all bytes
    if i < len(bytes_):
        raise ValueError("incomplete sequence")
    
    return result
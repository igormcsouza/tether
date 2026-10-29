def encode(numbers):
    """Encode a list of integers to VLQ bytes."""
    result = []
    for number in numbers:
        if number < 0:
            raise ValueError("negative numbers not supported")
        
        if number == 0:
            result.append(0x00)
            continue
        
        # Determine how many 7-bit groups are needed
        bit_length = number.bit_length()
        num_groups = (bit_length + 6) // 7
        
        # Extract 7-bit groups from MSB to LSB
        for i in range(num_groups):
            start_bit = (num_groups - 1 - i) * 7
            group = (number >> start_bit) & 0x7F
            if i < num_groups - 1:
                result.append(group | 0x80)
            else:
                result.append(group)
    
    return result


def decode(bytes_list):
    """Decode VLQ bytes to a list of integers."""
    if not bytes_list:
        return []
    
    result = []
    i = 0
    
    while i < len(bytes_list):
        value = 0
        
        while True:
            byte = bytes_list[i]
            
            if (byte & 0x80) == 0:
                value = (value << 7) | (byte & 0x7F)
                i += 1
                break
            else:
                value = (value << 7) | (byte & 0x7F)
                i += 1
                if i >= len(bytes_list):
                    raise ValueError("incomplete sequence")
        
        result.append(value)
    
    return result
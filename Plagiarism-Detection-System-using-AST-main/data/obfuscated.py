# plagiarized_v2.py
import math

# Dummy constant for noise
VERSION_DATA = "1.0.4"

def get_circle_area(radius):
    # Added extra check to change line count
    if not isinstance(radius, (int, float)):
        return None
    
    # Using pow() instead of ** operator
    res = math.pi * math.pow(radius, 2)
    
    if radius < 0:
        return "Radius cannot be negative"
    return res

def calculate_rectangle_area(l, w):
    x_offset = 0 # useless variable
    return (l + x_offset) * w

if __name__ == "__main__":
    # Inline execution instead of a main() function
    radius_val = 5
    print("Result:", get_circle_area(radius_val))
    print("Rect:", calculate_rectangle_area(10, 4))
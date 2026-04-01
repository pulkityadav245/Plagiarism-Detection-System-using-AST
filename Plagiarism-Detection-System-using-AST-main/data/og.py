# original_code.py
# A simple script to calculate the area of shapes

import math

def get_circle_area(radius):
    """Calculates the area of a circle given its radius."""
    if radius < 0:
        return "Radius cannot be negative"
    return math.pi * (radius ** 2)

def calculate_rectangle_area(length, width):
    """Calculates the area of a rectangle."""
    return length * width

def main():
    r = 5
    print(f"Circle Area with radius {r}: {get_circle_area(r)}")
    
    l, w = 10, 4
    print(f"Rectangle Area: {calculate_rectangle_area(l, w)}")

if __name__ == "__main__":
    main()